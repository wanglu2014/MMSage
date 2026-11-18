


MC <- Sys.getenv("MMSAGE_JOB_DIR")
if (!nzchar(MC)) stop("MMSAGE_JOB_DIR must identify the job input directory")
OUT <- Sys.getenv("MMSAGE_OUTPUT_DIR", unset=file.path(MC, "mmsage_out"))
dir.create(file.path(OUT, "pluscomb"), showWarnings=FALSE, recursive=TRUE)

cat("========== MMSage M3: pluscombno1 ==========\n")

cache <- readRDS(file.path(OUT, "M1_cache.rds"))
clr_mic <- t(cache$clr_mic)   
clr_met <- t(cache$clr_met)   
target_cags <- cache$all_target_cags


commrow <- rownames(clr_mic)
stopifnot(identical(commrow, rownames(clr_met)))

cat("Samples:", length(commrow), "| Metabolites:", ncol(clr_met), "| Target CAGs:", length(target_cags), "\n")

for (m in target_cags) {
  vecY <- clr_mic[, m]
  met_for_run <- clr_met
  scor_mat <- met_for_run * vecY
  long_df <- data.frame(
    samples = rep(commrow, times=ncol(met_for_run)),
    rowcolumn = rep(paste(colnames(met_for_run), m, sep="-"), each=length(commrow)),
    sCor = as.vector(scor_mat),
    stringsAsFactors = FALSE
  )
  out_file <- file.path(OUT, "pluscomb", paste0("pluscombno1_", m, ".csv"))
  write.csv(long_df, out_file, row.names=FALSE)
  cat("  ", m, "-> rows:", nrow(long_df), "\n")
}

cat("\nM3complete: ", file.path(OUT, "pluscomb/"), "\n")
