# MMSage Platform

MMSage connects two analyses. **Correlation ranking** ranks metabolites by their association with each microbe across shared samples. **Candidate evaluation** takes those ranked pairs and shows the literature and database evidence that connects each pair to a disease.

## Example files

| File | What it contains | Where to use it |
| --- | --- | --- |
| [microbes.tsv](TreeMM/Example/input/microbes.tsv) | Numeric abundances for 466 microbial features across 20 samples. | First file field in Correlation ranking. |
| [metabolites.tsv](TreeMM/Example/input/metabolites.tsv) | Numeric abundances for 85 metabolites across 19 samples. All 19 sample IDs also occur in the microbial table. | Second file field in Correlation ranking. Use it together with `microbes.tsv`. |
| [example20.csv](frontend/demo/example20.csv) | The first 20 ranked metabolites for *Cyanobacteria* from the example analysis, with Spearman correlations, P values, significance flags, and ranks. | Ranking file field in Candidate evaluation. |

## How to use the two analyses

### 1. Correlation ranking

1. Open **?** next to the page title and choose **upload example data**. This fills the two file fields and sets the target to `Cyanobacteria` and the P-value threshold to `0.05`. To use your own data, choose a microbial table and a metabolite table in CSV or tab-separated format. Put unique feature names in the first column, sample IDs in the header, and numeric abundances in the remaining cells. At least three sample IDs must match across the two tables. Column order can differ.
2. Click **Generate ranked results**. The progress panel shows the four analysis stages and a live log. When the run finishes, the panel shows up to five rows. Within each microbe, the most positive Spearman correlation ranks first. The P-value threshold sets the `Significant` flag.
3. Choose **Download ranking CSV** to save `correlation_ranking.csv` for Candidate evaluation. Its columns are `Microbe`, `Metabolite`, `Correlation`, `P_value`, `Significant`, and `Rank`. Choose **Download results ZIP** for `trajectory_results.zip`, which includes trajectory coordinates, `trajectory_ranking.csv` (metabolites ordered by pseudotime within each configuration), and logs.

### 2. Candidate evaluation

1. Open **Candidate evaluation** to explore the saved IBD analysis. It displays 146 *Akkermansia muciniphila* candidate pairs immediately. Select a pair to view its evidence.
2. To run your own evaluation, choose the `correlation_ranking.csv` you just downloaded. To try the 20-pair example instead, open **?** beside the upload controls and choose **upload example data**. Either action fills the input field. Uploads accept UTF-8 CSV files up to 100 MiB. A custom ranking CSV needs at least `Microbe`, `Metabolite`, and `Rank`. Compatible coordinate CSVs can supply `Pseudotime` or `mmsage_norm` alongside the pair identifiers.
3. Enter the disease of interest and click **Upload & Analyze**. Keep the tab open until the analysis finishes. Select a pair to inspect its uploaded rank and available evidence for the microbe–metabolite, metabolite–disease, and microbe–disease relationships. To reopen an archived result, use **Results Catalog** and select its record.
4. To request a follow-up plan for the selected pair, choose **Generate Step 3 Protocol**. To start from a research question of your own, enter the question and any optional constraints, then click **Generate Standalone Protocol**.

## Frontend files

| File | What it does and when it is used |
| --- | --- |
| [pipeline.html](frontend/pipeline.html) | Implements the Correlation ranking form, example loader, progress log, ranking preview, and download controls. |
| [MMSage_Dashboard.html](frontend/MMSage_Dashboard.html) | Loads the styles and browser libraries used by the Candidate evaluation page. |
| [dashboard.compiled.js](frontend/dashboard.compiled.js) | Runs the Candidate evaluation interface. It loads the IBD example, submits a new ranking, and updates the plot and evidence when a candidate is selected. It also handles the two planning buttons. |
| [kg_evidence.js](frontend/kg_evidence.js) | Draws the selected candidate’s evidence graph. Selecting a node or edge reveals supporting records and available PubMed links. |
| [browse.html](frontend/browse.html) and [browse_record.html](frontend/browse_record.html) | The first page searches the Results Catalog. The second opens a matching candidate, shows its scores and evidence, and lets the reader download its record as JSON. |

## Backend and analysis files

### From abundance tables to a ranking

| File | Role in the analysis |
| --- | --- |
| [api_server.py](backend/api_server.py) | Connects both web forms to their analysis workers. It accepts uploads and returns progress, results, catalog records, and graph data to the frontend. |
| [reference_inputs.py](backend/reference_inputs.py) | Checks the two matrices, aligns shared samples by ID, and prepares the tables used by the R stages. |
| [correlation_job_runner.py](backend/correlation_job_runner.py) | Runs stages M1–M4, calculates the per-microbe Spearman ranking, and packages the CSV and trajectory outputs. |
| [M1_targets_clr.R](r_pipeline/M1_targets_clr.R) and [M2_root_select.R](r_pipeline/M2_root_select.R) | M1 selects features and transforms their abundances. M2 uses association statistics to select starting metabolites for the trajectories. |
| [M3_pluscombno1.R](r_pipeline/M3_pluscombno1.R) and [M4_trajectory.R](r_pipeline/M4_trajectory.R) | M3 calculates microbe–metabolite interaction values within each sample. M4 uses the interaction matrices and selected roots to calculate coordinates and pseudotime. |
| [runtime.R](r_pipeline/trajectory_core/runtime.R), [settings.R](r_pipeline/trajectory_core/settings.R), and [upstream.R](r_pipeline/trajectory_core/upstream.R) | Supply M4 with its R package checks, default settings, and trajectory algorithms. The bundled code’s license is in [LICENSE](r_pipeline/trajectory_core/LICENSE). |

### From a ranking to candidate evidence

| File | Role in the analysis |
| --- | --- |
| [job_runner.py](backend/job_runner.py) and [run_pipeline.py](backend/run_pipeline.py) | Start an evaluation for the uploaded CSV and selected disease, then run candidate extraction, graph construction, evidence scoring, and archiving in order. |
| [runtime_state.py](backend/runtime_state.py) and [upload_lease.py](backend/upload_lease.py) | Record job status and track the browser session while an evaluation is queued or running. |
| [step1_mmsage_signal.py](backend/step1_mmsage_signal.py) | Extracts unique pairs from ranks or coordinates. For ranked uploads, it retains the best uploaded rank for each pair and passes up to 200 unique pairs to evaluation. |
| [build_kg.py](backend/build_kg.py), [knowledge_pump.py](backend/knowledge_pump.py), and [step2_chain_novelty.py](backend/step2_chain_novelty.py) | Build a disease-specific graph from the literature, find paths for each candidate, and combine those paths with PubMed co-occurrence counts to score chain novelty. |
| [step3_quadrant.py](backend/step3_quadrant.py) and [export_catalog.py](backend/export_catalog.py) | Classify pairs by signal and chain novelty, then archive the scores and evidence for browsing in the Results Catalog. |
| [validation_planner.py](backend/validation_planner.py), [protocol_refiner.py](backend/protocol_refiner.py), [protocols_io_tool.py](backend/protocols_io_tool.py), and [llm_reasoning.py](backend/llm_reasoning.py) | The Step 3 planning buttons use these modules to draft plans, review their components, retrieve methods references, and make model requests. |

### Literature and database lookups

| Files | How Candidate evaluation uses them |
| --- | --- |
| [agents package initializer](backend/agents/__init__.py) and [database checker package initializer](backend/db_checkers/__init__.py) | Expose the evidence agents and database lookup functions for use by the evaluation pipeline. |
| [master_agent.py](backend/agents/master_agent.py), [microbe_metabolite_agent.py](backend/agents/microbe_metabolite_agent.py), [metabolite_disease_agent.py](backend/agents/metabolite_disease_agent.py), and [microbe_disease_agent.py](backend/agents/microbe_disease_agent.py) | The master agent calls the three relationship-specific agents in parallel to collect evidence for each candidate. |
| [pubmed_query.py](backend/agents/pubmed_query.py), [hop_evidence.py](backend/agents/hop_evidence.py), and [evidence_aggregator.py](backend/agents/evidence_aggregator.py) | Build PubMed searches, record the evidence for each relationship, and combine the three records for display and scoring. |
| [bacdive_checker.py](backend/db_checkers/bacdive_checker.py), [binded_checker.py](backend/db_checkers/binded_checker.py), and [disbiome_checker.py](backend/db_checkers/disbiome_checker.py) | Retrieve microbial context from BacDive, reported microbe–compound pairs from BindedDB, and disease associations from Disbiome. |
| [chebi_checker.py](backend/db_checkers/chebi_checker.py) and [ctd_checker.py](backend/db_checkers/ctd_checker.py) | Retrieve chemical relationships from ChEBI and chemical–disease associations from CTD. |
| [build_sapbert_index.py](backend/db_checkers/build_sapbert_index.py) and [sapbert_retriever.py](backend/db_checkers/sapbert_retriever.py) | The first builds a searchable index of reference names. The second matches names during database lookups. |

## Run the application locally

From the project root, use Python 3.10 or later and install the dependencies in [requirements.txt](requirements.txt). Correlation ranking also requires R with the packages in [packages.txt](r_pipeline/trajectory_core/packages.txt) and `Rscript` available on your path.

```bash
python -m pip install -r requirements.txt
python -m uvicorn backend.api_server:app
```

Open the local address printed by Uvicorn to use the two example workflows. Fresh evidence searches use PubMed and the project’s reference databases. Model-assisted graph extraction and follow-up planning also use a configured model API.
