

import csv
import io
import re
import json
import glob
from pathlib import Path
from typing import BinaryIO, Optional

import pandas as pd
import numpy as np


def extract_bacteria_from_filename(filename: str) -> Optional[str]:
    pass
    base = Path(filename).stem  
    
    m = re.search(r'_min\d+_(.+?)_seed_', base)
    if m:
        return m.group(1)
    
    m = re.search(r'_([A-Z][a-z]+_[a-z]+(?:_[a-z]+)*)_seed_', base)
    if m:
        return m.group(1)
    return None


def parse_metabolite_from_rowname(rowname: str, bacteria: str) -> str:
    pass
    
    rowname = rowname.strip().strip('"')
    
    suffix = f"-{bacteria}"
    if suffix in rowname:
        return rowname.split(suffix)[0]
    
    parts = rowname.rsplit('-', 1)
    if len(parts) == 2:
        return parts[0]
    return rowname


RANK_COLUMNS = ("MMSage rank", "Rank", "rank")


def validate_coordinate_format(stream: BinaryIO) -> None:
    """Check the CSV header without consuming the upload or loading its data rows."""
    position = stream.tell()
    try:
        stream.seek(0)
        sample = stream.read(128 * 1024)
        if sample.startswith((b"PK\x03\x04", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")):
            raise ValueError("Workbook or archive detected. Export the coordinate sheet as UTF-8 CSV and upload it again.")
        if len(sample) == 128 * 1024:
            boundary = max(sample.rfind(b"\n"), sample.rfind(b"\r"))
            sample = sample[:boundary + 1]
        try:
            with io.TextIOWrapper(io.BytesIO(sample), encoding="utf-8-sig", newline="") as reader:
                columns = next((row for row in csv.reader(reader, strict=True) if row), [])
        except (csv.Error, UnicodeDecodeError) as exc:
            raise ValueError("Invalid CSV format.") from exc
        if len(columns) < 2 or not set(columns).intersection((*RANK_COLUMNS, "Pseudotime", "mmsage_norm")):
            raise ValueError("Invalid CSV format.")
        if set(columns).intersection(RANK_COLUMNS) and not set(columns).intersection({
            "metabolite", "Metabolite", "comp.name", "Compound_Name", "metabolite_id", "Row.names", "rowcolumn", "CellID",
        }):
            raise ValueError("Invalid CSV format.")
    finally:
        stream.seek(position)


def _candidate_names(df: pd.DataFrame, filename: str, *, ranked: bool = False) -> pd.DataFrame:
    """Read explicit pair names or the pair identifiers in MMSage coordinate exports."""
    names = pd.DataFrame(index=df.index)
    labels = next((col for col in ("Row.names", "rowcolumn", "CellID") if col in df), None)
    bacteria_cols = ["bacteria", "Microbe", "microbe"]
    metabolite_cols = ["metabolite", "Metabolite"]
    if ranked:
        # Annotated exports store an ASV sequence in Microbe and its taxon in species.
        bacteria_cols = ["species", *bacteria_cols, "microbe_id"]
        metabolite_cols += ["comp.name", "Compound_Name", "metabolite_id"]

    def first_named_value(columns):
        values = pd.Series(pd.NA, index=df.index, dtype="string")
        for col in columns:
            if col in df:
                values = values.fillna(df[col].astype("string").str.strip().replace("", pd.NA))
        return values

    bacteria_col = next((col for col in bacteria_cols if col in df), None)
    metabolite_col = next((col for col in metabolite_cols if col in df), None)

    if bacteria_col:
        names["bacteria"] = first_named_value(bacteria_cols)
    elif "Configuration" in df:
        names["bacteria"] = df["Configuration"].astype("string").str.extract(
            r"^coords_(.+)_seed\d+_.+_NArank\d+$", expand=False
        )
    else:
        bacteria = extract_bacteria_from_filename(filename)
        if not bacteria:
            if labels is not None:
                suffixes = df[labels].astype("string").str.strip().str.extract(
                    r"^.+-([A-Z][a-z]+_[a-z]+(?:_[A-Za-z0-9]+)*)$", expand=False
                )
                if suffixes.notna().all() and suffixes.nunique() == 1:
                    bacteria = suffixes.iloc[0]
            if not bacteria:
                raise ValueError(
                    "Cannot identify the microbe. Include a Microbe column, a single species "
                    "suffix in Row.names, or the original MMSage coordinate filename."
                )
        names["bacteria"] = bacteria

    if names["bacteria"].isna().any() or names["bacteria"].eq("").any():
        raise ValueError("Include a Microbe name for every row or use a valid trajectory Configuration.")
    if "Configuration" in df:
        configs = df["Configuration"].astype("string").str.strip()
        if configs.isna().any() or configs.eq("").any() or configs.groupby(names["bacteria"]).nunique().gt(1).any():
            raise ValueError("Select one trajectory configuration per microbe before uploading.")

    if metabolite_col:
        names["metabolite"] = first_named_value(metabolite_cols)
    else:
        if labels is None:
            if ranked:
                raise ValueError("Invalid CSV format.")
            # Older coordinate CSVs store their row names in an unnamed text column.
            labels = df.columns[1] if df.columns[0].startswith("Unnamed") and len(df.columns) > 1 else df.columns[0]
        if labels in {bacteria_col, "Configuration", "Pseudotime", "mmsage_norm", "Rank"}:
            raise ValueError("Include a Metabolite or Row.names column for the candidate names.")
        names["metabolite"] = [
            parse_metabolite_from_rowname(str(value), bacteria) if pd.notna(value) else ""
            for value, bacteria in zip(df[labels], names["bacteria"])
        ]
    if names["metabolite"].isna().any() or names["metabolite"].eq("").any():
        raise ValueError("Include a metabolite name for every candidate.")
    return names


def process_single_file(
    filepath: str,
    top_n: int = 200,
) -> list:
    fpath = Path(filepath)
    with fpath.open("rb") as stream:
        validate_coordinate_format(stream)
        try:
            df = pd.read_csv(stream, float_precision="round_trip")
        except (UnicodeDecodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
            raise ValueError("Invalid CSV format.") from exc

    rank_col = next((col for col in RANK_COLUMNS if col in df), None)
    if rank_col is None and not {"Pseudotime", "mmsage_norm"}.intersection(df):
        raise ValueError("Invalid CSV format.")
    if df.empty:
        raise ValueError("The uploaded CSV contains no candidates.")
    candidates = _candidate_names(df, fpath.name, ranked=rank_col is not None)
    candidates["source_file"] = str(fpath)

    if "mmsage_norm" in df:
        signal = pd.to_numeric(df["mmsage_norm"], errors="coerce")
        if not signal.between(0, 1).all():
            raise ValueError("Each mmsage_norm must be a finite number between 0 and 1.")
        candidates["mmsage_norm"] = signal
    if rank_col is not None:
        ranks = pd.to_numeric(df[rank_col], errors="coerce")
        if not (ranks.ge(0) & np.isfinite(ranks)).all():
            raise ValueError("Invalid CSV format.")
        candidates["uploaded_rank"] = ranks
        candidates = candidates.sort_values("uploaded_rank", kind="stable").drop_duplicates(["bacteria", "metabolite"])
        if "mmsage_norm" not in candidates:
            # Supply the existing signal axis with an order-preserving percentile.
            positions = candidates["uploaded_rank"].rank(method="min")
            candidates["mmsage_norm"] = 1.0 - (positions - 1) / len(candidates)
        return candidates.head(top_n).to_dict(orient="records")

    if "mmsage_norm" not in df:
        pt = pd.to_numeric(df["Pseudotime"], errors="coerce")
        if (df["Pseudotime"].notna() & (pt.isna() | ~np.isfinite(pt))).any():
            raise ValueError("Pseudotime values must be finite numbers.")
        candidates = candidates.loc[pt.notna()].copy()
        pt = pt.loc[candidates.index]
        groups = candidates["bacteria"]
        max_pt = pt.groupby(groups).transform("max")
        if pt.empty or (max_pt <= 0).any():
            raise ValueError("Each microbe needs a positive maximum Pseudotime.")
        # The original Step 1 score uses the distance to the nearest trajectory end.
        distance = np.minimum(pt, max_pt - pt)
        position = distance.groupby(groups).rank(ascending=True, method="first")
        count = pt.groupby(groups).transform("size")
        candidates["pseudotime"] = pt.round(4)
        candidates["mmsage_norm"] = 1.0 - (position - 1) / count
        candidates["rank_in_microbe"] = pt.groupby(groups).rank(ascending=False, method="first").astype(int)
        candidates["total_in_microbe"] = count

    candidates = candidates.sort_values("mmsage_norm", ascending=False)
    candidates = candidates.drop_duplicates(["bacteria", "metabolite"]).head(top_n).copy()
    if "mmsage_norm" not in df:
        candidates["mmsage_norm"] = candidates["mmsage_norm"].round(4)
    return candidates.to_dict(orient="records")


def process_coordinates_dir(
    coordinates_dir: str,
    top_n: int = 200,
    bacteria_filter: Optional[str] = None,
) -> list:
    pass
    coord_dir = Path(coordinates_dir)
    pattern = str(coord_dir / "*_coordinates_tunek.csv")
    files = glob.glob(pattern)

    if not files:
        raise FileNotFoundError(
            f"No *_coordinates_tunek.csv files found in {coordinates_dir}"
        )

    print(f"Found {len(files)} coordinates files")

    if bacteria_filter:
        files = [f for f in files if bacteria_filter in f]
        print(f"Filtered to {len(files)} files containing '{bacteria_filter}'")

    all_candidates = []

    for i, filepath in enumerate(files):
        fname = Path(filepath).name
        bacteria = extract_bacteria_from_filename(fname)
        if not bacteria:
            continue

        try:
            df = pd.read_csv(filepath)
        except Exception:
            continue

        
        if 'Pseudotime' not in df.columns:
            continue

        
        rowname_col = None
        if 'Row.names' in df.columns:
            rowname_col = 'Row.names'
        elif df.columns[0] == '' or df.columns[0].startswith('Unnamed'):
            
            if len(df.columns) > 1 and 'Row.names' in df.columns.tolist():
                rowname_col = 'Row.names'
            else:
                rowname_col = df.columns[1] if len(df.columns) > 1 else df.columns[0]
        else:
            rowname_col = df.columns[0]

        
        max_pt = df['Pseudotime'].max()
        if max_pt <= 0 or pd.isna(max_pt):
            continue

        for _, row in df.iterrows():
            rowname = str(row.get(rowname_col, ''))
            metabolite = parse_metabolite_from_rowname(rowname, bacteria)
            pseudotime = row['Pseudotime']

            if pd.isna(pseudotime):
                continue

            all_candidates.append({
                'bacteria': bacteria,
                'metabolite': metabolite,
                'pseudotime': float(pseudotime),
                'max_pseudotime': float(max_pt),
                'source_file': filepath,
            })

        if (i + 1) % 500 == 0:
            print(f"  Processed {i + 1}/{len(files)} files, "
                  f"{len(all_candidates)} pairs so far")

    print(f"Total raw pairs: {len(all_candidates)}")

    if not all_candidates:
        return []

    
    df_all = pd.DataFrame(all_candidates)

    
    def _rank_dual_end(group):
        pt = group['pseudotime']
        pt_max = pt.max()
        dist_to_end = pt.apply(lambda x: min(x, pt_max - x))
        n = len(group)
        rank = dist_to_end.rank(ascending=True, method='first')
        group['mmsage_norm'] = 1.0 - (rank - 1) / n
        group['rank_in_microbe'] = pt.rank(ascending=False, method='first').astype(int)
        group['total_in_microbe'] = n
        return group

    df_all = df_all.groupby('bacteria', group_keys=False).apply(_rank_dual_end)
    
    if 'bacteria' not in df_all.columns:
        df_all = df_all.reset_index()

    
    df_all = df_all.sort_values('mmsage_norm', ascending=False)

    
    df_dedup = df_all.drop_duplicates(subset=['bacteria', 'metabolite'], keep='first')
    df_top = df_dedup.head(top_n)

    
    results = []
    for _, row in df_top.iterrows():
        results.append({
            'bacteria': row['bacteria'],
            'metabolite': row['metabolite'],
            'pseudotime': round(row['pseudotime'], 4),
            'mmsage_norm': round(row['mmsage_norm'], 4),
            'rank_in_microbe': int(row['rank_in_microbe']),
            'total_in_microbe': int(row['total_in_microbe']),
            'source_file': row['source_file'],
        })

    print(f"Returning top {len(results)} candidates")
    return results


def run_step1(
    coordinates_dir: str,
    output_path: str,
    top_n: int = 200,
    bacteria_filter: Optional[str] = None,
    coordinates_file: Optional[str] = None,
) -> list:
    pass
    print("=" * 60)
    print("  STEP 1: MMSage Signal Processing")
    print("=" * 60)

    if coordinates_file:
        candidates = process_single_file(coordinates_file, top_n)
    else:
        candidates = process_coordinates_dir(coordinates_dir, top_n, bacteria_filter)

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(candidates, f, indent=2, ensure_ascii=False)

    print(f"Saved {len(candidates)} candidates to {output_path}")
    return candidates


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Step 1: MMSage Signal Processing')
    _project_dir = str(Path(__file__).parent.parent)
    parser.add_argument('--coordinates-dir',
                        default=_project_dir + '/data/sample_coordinates',
                        help='Path to coordinates CSV directory')
    parser.add_argument('--output', default='outputs/step1_candidates.json')
    parser.add_argument('--top-n', type=int, default=200)
    parser.add_argument('--bacteria-filter', default=None,
                        help='Only process files containing this string')
    parser.add_argument('--coordinates-file',
                        default=_project_dir + '/data/sample_coordinates/pluscombno1V0317_min0_Akkermansia_muciniphila_seed_1_dim_10_neighbor_2_dist_0.4_metric_euclidean_rank_rootknow_cor0303_1_top_50_Pthre_0.1_pair.csv_clu_1_coordinates_tunek.csv',
                        help='Process a single coordinates CSV file instead of directory')
    args = parser.parse_args()

    run_step1(args.coordinates_dir, args.output, args.top_n, args.bacteria_filter,
              coordinates_file=args.coordinates_file)
