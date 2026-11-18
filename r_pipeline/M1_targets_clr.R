

MC <- Sys.getenv("MMSAGE_JOB_DIR")
if (!nzchar(MC)) stop("MMSAGE_JOB_DIR must identify the job input directory")
OUT <- Sys.getenv("MMSAGE_OUTPUT_DIR", unset=file.path(MC, "mmsage_out"))
dir.create(OUT, showWarnings=FALSE, recursive=TRUE)

cat("========== MMSage M1: Input features + CLR ==========\n")

mic <- read.table(file.path(MC,"data/microbes_wide.tsv"), header=TRUE, sep="\t",
                 check.names=FALSE, row.names=1, quote='"', comment.char="")
met <- read.table(file.path(MC,"data/metabolites_wide.tsv"), header=TRUE, sep="\t",
                 check.names=FALSE, row.names=1, quote='"', comment.char="")
met_threshold <- suppressWarnings(as.numeric(Sys.getenv("MMSAGE_MIN_METABOLITE_MEAN", unset="0.0026")))
if (!is.finite(met_threshold) || met_threshold < 0) met_threshold <- 0
met_norm <- sweep(as.matrix(met), 2, pmax(colSums(as.matrix(met), na.rm=TRUE), 1e-12), "/")
keep_met <- rowMeans(met_norm, na.rm=TRUE) >= met_threshold
if (!any(keep_met)) stop("No metabolites remain after the configured abundance threshold")
cat("Microbes:", nrow(mic),"x",ncol(mic)," Metabolites:",sum(keep_met),"/",nrow(met),"\n")

all_target_cags <- rownames(mic)
requested_microbe <- trimws(Sys.getenv("MMSAGE_MICROBE_FILTER", unset=""))
if (nzchar(requested_microbe)) {
  exact <- all_target_cags[tolower(all_target_cags) == tolower(requested_microbe)]
  fuzzy <- all_target_cags[grepl(requested_microbe, all_target_cags, fixed=TRUE, ignore.case=TRUE)]
  target_cags <- unique(c(exact, fuzzy))
  if (!length(target_cags)) stop("Requested microbe or taxon is absent from the input: ", requested_microbe)
} else {
  target_cags <- all_target_cags
}
targets <- lapply(target_cags, function(x) list(microbe=x, metabolite=rownames(met), direction=NA_integer_))
target_mets <- list(input_metabolites=rownames(met))
taxon <- data.frame(CAG=all_target_cags, species=all_target_cags, stringsAsFactors=FALSE)
cat("Input microbe count:", length(target_cags), "| Input metabolite count:", nrow(met), "\n")



rclr <- function(feature_by_sample) {
  x <- t(as.matrix(feature_by_sample))
  x[is.na(x)] <- 0
  totals <- rowSums(x, na.rm=TRUE)
  x <- x / pmax(totals, 1e-12)
  z <- log(x)
  z[is.infinite(z) | is.na(z)] <- NA_real_
  center <- rowMeans(z, na.rm=TRUE)
  centered <- sweep(z, 1, center, "-")
  centered[is.infinite(centered) | is.na(centered)] <- NA_real_
  t(centered)
}

clr_mic <- rclr(mic)


met_raw <- as.matrix(met)
met_norm_full <- t(sweep(met_raw, 2, pmax(colSums(met_raw, na.rm=TRUE), 1e-12), "/"))
met_norm_full <- met_norm_full[, keep_met, drop=FALSE]
z_met <- log(met_norm_full)
z_met[is.infinite(z_met) | is.na(z_met)] <- NA_real_
z_met <- sweep(z_met, 1, rowMeans(z_met, na.rm=TRUE), "-")
z_met[is.infinite(z_met) | is.na(z_met)] <- NA_real_
clr_met <- t(z_met)
met <- met[keep_met, , drop=FALSE]

stopifnot(identical(dim(clr_mic), dim(as.matrix(mic))),
          identical(dim(clr_met), dim(as.matrix(met))))
cat("CLR complete clr_mic:", dim(clr_mic), "clr_met:", dim(clr_met), "\n")

saveRDS(list(targets=targets, target_cags=target_cags, all_target_cags=target_cags,
             target_mets=list(input_metabolites=rownames(met)), clr_mic=clr_mic, clr_met=clr_met, taxon=taxon),
        file.path(OUT,"M1_cache.rds"))
cat("Saved: mmsage_out/M1_cache.rds\n")
cat("========== M1 complete ==========\n")
