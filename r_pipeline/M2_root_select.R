

MC <- Sys.getenv("MMSAGE_JOB_DIR")
if (!nzchar(MC)) stop("MMSAGE_JOB_DIR must identify the job input directory")
OUT <- Sys.getenv("MMSAGE_OUTPUT_DIR", unset=file.path(MC, "mmsage_out"))
dir.create(file.path(OUT, "roots"), showWarnings=FALSE, recursive=TRUE)

cat("========== MMSage M2: Root selection (Noback) ==========\n")

cache <- readRDS(file.path(OUT, "M1_cache.rds"))
clr_met <- cache$clr_met
all_target_cags <- cache$all_target_cags

cor_mat <- as.matrix(read.table(file.path(MC, "results/method02_spearman_matrix.tsv"),
                                header=TRUE, sep="\t", row.names=1, check.names=FALSE, quote='"', comment.char=""))
pval_mat <- as.matrix(read.table(file.path(MC, "results/method02_spearman_pvalues.tsv"),
                                 header=TRUE, sep="\t", row.names=1, check.names=FALSE, quote='"', comment.char=""))
cat("Spearman matrix:", nrow(cor_mat), "x", ncol(cor_mat), "\n")



met_root <- read.table(file.path(MC, "data/metabolites_wide.tsv"), header=TRUE,
                       sep="\t", check.names=FALSE, row.names=1, quote='"', comment.char="")
met_root <- as.matrix(met_root)
positive_root <- met_root[is.finite(met_root) & met_root > 0]
if (!length(positive_root)) stop("Metabolite table has no positive values")
met_root[met_root == 0] <- min(positive_root)


met_root <- t(met_root)
met_root <- met_root / pmax(rowSums(met_root), 1e-12)
log_root <- log(met_root)
clr_met_root <- sweep(log_root, 1, rowMeans(log_root), "-")
clr_met_mean <- colMeans(clr_met_root, na.rm=TRUE)

NArank_grid <- c(1, 2, 3, 5)


p_thresh <- suppressWarnings(as.numeric(Sys.getenv("MMSAGE_ROOT_P_THRESHOLD", unset="1")))
if (!is.finite(p_thresh) || p_thresh < 0 || p_thresh > 1) p_thresh <- 1

all_roots <- list()

for (cag in all_target_cags) {
  if (!cag %in% rownames(cor_mat)) {
    cat("  ", cag, " is absent from the Spearman matrix; skipping\n")
    next
  }
  cors <- cor_mat[cag, ]
  pvals <- pval_mat[cag, ]

  
  
  valid <- which(names(cors) %in% colnames(met_root) & !is.na(cors) &
                 !is.na(pvals) & cors > 0 & pvals < p_thresh)
  if (length(valid) == 0) {
    
    
    
    valid <- which(names(cors) %in% colnames(met_root) & !is.na(cors) & is.finite(cors) & cors > 0)
    if (length(valid) == 0) {
      valid <- which(names(cors) %in% colnames(met_root) & !is.na(cors) & is.finite(cors))
    }
    if (length(valid) == 0) {
      cat("  ", cag, " has no available correlations; skipping\n")
      next
    }
    cat("  ", cag, " has no significant positive correlations; using the metabolite with the strongest correlation as the fallback root\n")
  }

  valid_mets <- names(cors)[valid]
  valid_means <- clr_met_mean[valid_mets]
  sorted_mets <- valid_mets[order(valid_means, decreasing=TRUE)]

  for (nar in NArank_grid) {
    roots <- head(sorted_mets, nar)
    for (r in roots) {
      all_roots[[length(all_roots)+1]] <- data.frame(
        CAG=cag, Root=r, NArank=nar,
        Cor=cors[r], Pval=pvals[r], CLR_mean=clr_met_mean[r],
        stringsAsFactors=FALSE)
    }
  }
  cat("  ", cag, ": positively correlated metabolites: ", length(valid), "; top 5 root candidates:",
      paste(head(sorted_mets,5), collapse=","), "\n")
}

roots_df <- do.call(rbind, all_roots)
write.csv(roots_df, file.path(OUT, "roots/all_roots_noback.csv"), row.names=FALSE)
cat("\nRoot selection complete:", nrow(roots_df), " entries (", length(unique(roots_df$CAG)), " CAGs)\n")
cat("NArank distribution:\n")
print(table(roots_df$NArank))
cat("Saved: mmsage_out/roots/all_roots_noback.csv\n")
cat("========== M2 complete ==========\n")
