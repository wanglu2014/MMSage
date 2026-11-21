# MMSage Platform

MMSage connects ranked microbe–metabolite pairs to disease-specific evidence from PubMed, biological databases, and knowledge graphs. The dashboard preserves uploaded ranks and lets readers inspect the evidence for each candidate. A separate abundance workflow produces ranking tables and trajectory coordinates from paired microbial and metabolite matrices.

## How the code runs

From the repository root, install the Python dependencies into an active Python 3.10+ environment and start the web service.

```bash
python -m pip install -r requirements.txt
python -m uvicorn backend.api_server:app --host 127.0.0.1 --port 8000
```

Uvicorn imports the FastAPI application from `backend/api_server.py`. FastAPI serves the HTML pages and exposes `frontend/` at `/static`. At `/dashboard`, the browser executes `dashboard.compiled.js` and calls the Python API over HTTP. The browser loads React, Plotly, Cytoscape, and other frontend libraries from CDNs.

### From an uploaded ranking to an interactive graph

1. **Submit the file.** **Upload & Process** sends the CSV and disease to `POST /api/upload-coordinates`. The server stores the input under `data/jobs/<job_id>/inputs/`, starts `job_runner.py` as a child process, and returns a `job_id`. The browser polls `GET /api/jobs/{job_id}/status` while the worker runs.
2. **Read the ranks.** The worker calls `run_pipeline()`, which passes the CSV to `step1_mmsage_signal.py`. A minimal ranked input has `Microbe`, `Metabolite`, and `Rank` columns. The parser also accepts `MMSage rank` and `rank` as rank headers. It sorts finite nonnegative ranks in ascending order, keeps the lowest rank for duplicate pairs, and preserves input order for ties. The dashboard worker takes the first 200 unique pairs. Each retains its original `uploaded_rank`. When the file omits `mmsage_norm`, the parser derives a normalized signal from rank positions for the plot.
3. **Collect evidence.** The pipeline launches `build_kg.py candidates` to retrieve articles and build a graph for the run. If the graph-building subprocess fails, the pipeline attempts scoring with the configured fallback graph. `step2_chain_novelty.py` uses `KnowledgePump` and PubMed counts to score the candidates. For each candidate, `MasterAgent` runs three pairwise checks in parallel. The pipeline writes their queries, counts, and database results to `step2b_agent_evidence.json`.
4. **Archive and display the result.** `step3_quadrant.py` assigns quadrants and retains the uploaded rank. `export_catalog.py` archives the results under `data/results_catalog/runs/<run_id>/`. Once the job reports `done`, the browser uses its `run_id` to fetch `/api/dual-axis-candidates` and update the URL. Selecting a candidate requests `/api/graph/chain` with `view=agent` and the same run ID. A dashboard click shows the evidence attached to the selected edge or to a node’s incident edges. The catalog record page fetches node details separately through `/api/graph/node-evidence`.
5. **Request a follow-up plan.** For a selected candidate, **Generate Step 3 Protocol** calls `POST /api/validation-plan/start`. The server starts a separate planning job. The browser polls `/api/validation-plan/status/{job_id}` for the result. This dashboard action runs on demand, after the upload pipeline has finished its own Step 3 quadrant assignment.

The dashboard accepts UTF-8 CSV files up to 100 MiB. It reports an error if the upload request or the worker's initial CSV loading stage exceeds 120 seconds. Evidence collection starts after CSV loading completes and has its own runtime.

Keep the dashboard tab open while a coordinate upload is queued or being analyzed. The tab sends a heartbeat every 15 seconds. Closing or reloading it requests a pause. If the browser disconnects without sending the request, the worker pauses after 90 seconds without a heartbeat. A paused upload keeps its input on disk and releases the analysis slot. To run it again, submit the CSV as a new upload. Once catalog publication has started, the worker finishes saving the result.

New evidence searches use PubMed and local reference tables in `data/databases/`. Semantic entity matching uses the SapBERT index under `backend/db_checkers/sapbert_index/`. Model-backed planning reads `OPENAI_API_KEY`, `OPENAI_API_BASE`, and `OPENAI_MODEL` from the server environment.

### From abundance matrices to ranking files

1. At `/pipeline`, `pipeline.html` sends two abundance matrices to `POST /api/correlation/jobs`. Rows identify microbes or metabolites and columns identify samples. `reference_inputs.py` requires at least three shared sample IDs, aligns those columns, and stages the tables used by R.
2. `correlation_job_runner.py` finds `Rscript` on `PATH` or at `MMSAGE_RSCRIPT`, checks the trajectory runtime, then launches M1 through M4 as separate processes. They exchange files in the job directory. M1 writes the transformed abundance cache. M2 uses it to select roots, and M3 uses it to build interaction matrices. M4 reads all three outputs to compute coordinates and pseudotime.
3. The Python worker calculates `correlation_ranking.csv` from the shared-sample abundances, ranking metabolites within each microbe by descending Spearman correlation. It reads the M4 coordinates to write `trajectory_ranking.csv` in ascending pseudotime order within each configuration. The page provides the correlation CSV and `trajectory_results.zip`. Submit the correlation CSV directly through **Upload Coordinates CSV** for disease-specific evidence analysis. To submit the trajectory ranking from the ZIP, select one configuration per microbe first.

## Project dependencies

| File | How it runs | Role |
| --- | --- | --- |
| [requirements.txt](requirements.txt) | Read by pip during environment setup. | Declares Python dependencies for FastAPI, numerical analysis, PubMed retrieval, model clients, job locking, and tests. |

## Web interface

| File | How it runs | Role |
| --- | --- | --- |
| [frontend/index.html](frontend/index.html) | Returned by FastAPI for `GET /`. The browser fetches quadrant data and pipeline status. | Shows the overall run status and plots candidates by signal and chain novelty. |
| [frontend/MMSage_Dashboard.html](frontend/MMSage_Dashboard.html) | Served for `GET /dashboard`. Its external script tag loads `dashboard.compiled.js`. | Provides the page layout, styles, and root element for the interactive dashboard. |
| [frontend/dashboard.compiled.js](frontend/dashboard.compiled.js) | Executed when the dashboard loads. Click handlers submit jobs and fetch data for the selected run. | Maintains the active run and candidate selection, displays upload progress, and updates the plot, evidence graph, and follow-up plan. |
| [frontend/kg_evidence.js](frontend/kg_evidence.js) | Loaded by the dashboard and record page. Its Cytoscape event handlers read the selected graph item and update the evidence panel. | Renders the candidate graph and its evidence panel. It handles node and edge selection and links article evidence to PubMed. |
| [frontend/browse.html](frontend/browse.html) | Served at `/browse`. Calls `/api/catalog/runs` and `/api/catalog/search` as filters change. | Lets readers filter archived candidates and open the matching record. |
| [frontend/browse_record.html](frontend/browse_record.html) | Served at `/browse/record`. Requests the record and graph using the run ID and candidate identifiers. | Combines the selected candidate’s scores, graph, and evidence in one downloadable record. |
| [frontend/candidate.html](frontend/candidate.html) | Served at `/candidate`. Fetches the selected pair’s record or looks it up in the stage results. | Displays the candidate detail view, including scores and evidence for the selected microbe–metabolite pair. |
| [frontend/evidence.html](frontend/evidence.html) | Served at `/evidence`. Reads archived agent results or submits a live pair lookup to `/api/agent/query`. | Displays the evidence returned by the microbe–metabolite, metabolite–disease, and microbe–disease agents. |
| [frontend/graph.html](frontend/graph.html) | Served at `/graph`. Fetches the full graph, a neighborhood, or a candidate chain according to the controls. | Provides the knowledge graph explorer for browsing entities and their relationships. |
| [frontend/pipeline.html](frontend/pipeline.html) | Served at `/pipeline`. Posts the matrices to `/api/correlation/jobs` and polls the returned job ID. | Collects abundance-matrix inputs and analysis settings, reports progress, and offers the result downloads. |

## Web service and analysis pipeline

| File | How it runs | Role |
| --- | --- | --- |
| [backend/api_server.py](backend/api_server.py) | Imported by Uvicorn as `backend.api_server:app`. Route handlers call the relevant service or launch a worker. | Defines the FastAPI routes for pages, uploads, job status, archived results, graph evidence, and validation plans. Resolves the run used for each dashboard request. |
| [backend/runtime_state.py](backend/runtime_state.py) | Imported by the API and workers whenever they resolve a job directory or read or update its status. | Defines paths for jobs and application state and writes JSON updates atomically. |
| [backend/job_runner.py](backend/job_runner.py) | Launched by the upload route with `--job-id`, `--csv-path`, and `--disease`. Calls `run_pipeline()` after acquiring the worker lock. | Runs a coordinate upload in its own job directory, serializes coordinate analyses with a file lock, and records progress, errors, and the final archive ID. |
| [backend/upload_lease.py](backend/upload_lease.py) | Called by the upload and heartbeat routes and by the coordinate worker. | Tracks the owning page, validates its pause requests, and protects catalog publication once it begins. |
| [backend/run_pipeline.py](backend/run_pipeline.py) | Called by `job_runner.py`. Invokes the Python scoring functions, starts the graph builder, and passes the outputs to `archive_run()`. | Sets the disease context and coordinates the analysis stages so that each stage receives the preceding results. |
| [backend/step1_mmsage_signal.py](backend/step1_mmsage_signal.py) | Called as `run_step1()` by `run_pipeline.py`. Writes `step1_candidates.json` for graph construction and scoring. | Extracts unique microbe–metabolite pairs from uploaded ranks, normalized signals, or pseudotime. For ranked inputs it keeps the best rank per pair and preserves the order of ties. |
| [backend/build_kg.py](backend/build_kg.py) | Launched as a Python subprocess with the `candidates` subcommand. Reads the Step 1 JSON and disease. | Writes PubMed article mentions to `literature_context.gml` before model extraction. Writes relationships extracted from abstracts to `knowledge_graph.gml`. |
| [backend/knowledge_pump.py](backend/knowledge_pump.py) | Instantiated as `KnowledgePump` during Step 2. Reads the GML selected for the run. | Loads GML graphs and retrieves entities, paths, and graph context for candidate scoring. |
| [backend/step2_chain_novelty.py](backend/step2_chain_novelty.py) | Called as `run_step2()` after graph construction. Writes `step2_chain_novelty.json` for subsequent evidence and quadrant analysis. | Combines candidate graph paths with PubMed co-occurrence counts to estimate chain novelty for the specified disease. |
| [backend/step3_quadrant.py](backend/step3_quadrant.py) | Called as `run_step3()` after agent results have been attached. Writes `step3_quadrant.json`. | Classifies candidates by signal and chain novelty, keeping their original uploaded ranks available to the dashboard and catalog. |
| [backend/export_catalog.py](backend/export_catalog.py) | Called by the pipeline to archive a completed run and by catalog endpoints to read its metadata and candidate records. | Maintains the Results Catalog index, supports filtered search, and combines stage outputs into per-candidate records. |
| [backend/llm_reasoning.py](backend/llm_reasoning.py) | Imported by `build_kg.py` and `protocol_refiner.py` for model configuration and request handling. | Builds model requests and parses structured reasoning responses. It retries a specific model-availability error through a supported alias. |
| [backend/validation_planner.py](backend/validation_planner.py) | Called by validation-plan API handlers. Receives the candidate, disease, and run ID and returns a structured plan and its text. | Combines candidate evidence, literature searches, and model reviews to generate the dashboard’s evidence-gap assessment and follow-up plan. |
| [backend/protocol_refiner.py](backend/protocol_refiner.py) | Called by the planner to review plan components and by the refinement endpoints to manage an editing session. | Manages refinement sessions, component reviews, and revisions to proposed plans. |
| [backend/protocols_io_tool.py](backend/protocols_io_tool.py) | Called by the planner through `collect_protocol_evidence()` during methods retrieval. | Searches public protocols.io records and retrieves methods references used by the validation planner. |
| [backend/reference_inputs.py](backend/reference_inputs.py) | Called through `stage_inputs()` by the abundance worker before the first R process starts. | Validates abundance matrices, aligns shared sample IDs, and prepares taxonomy, correlation, and P-value tables for the R stages. |
| [backend/correlation_job_runner.py](backend/correlation_job_runner.py) | Started in a background thread by `/api/correlation/jobs`. Sets the job paths for R and collects its outputs. | Produces per-microbe correlation rankings from the matrices and per-configuration pseudotime rankings from the R output. |

## Evidence agents

| File | How it runs | Role |
| --- | --- | --- |
| [backend/agents/__init__.py](backend/agents/__init__.py) | Executed on package import. Makes the agent types available from `agents`. | Exports the agent classes, shared evidence record, and aggregator. |
| [backend/agents/master_agent.py](backend/agents/master_agent.py) | Instantiated by `run_pipeline.py` and the live agent-query route. Calls the pairwise agents and `EvidenceAggregator.aggregate()`. | Runs the three checks concurrently and attaches their query results and combined assessment to the candidate. |
| [backend/agents/microbe_metabolite_agent.py](backend/agents/microbe_metabolite_agent.py) | Called by `MasterAgent.run()` with the microbe and metabolite. Returns a `HopEvidence` record. | Collects PubMed and BindedDB evidence for the microbe–metabolite pair, with microbial context from BacDive and Disbiome. |
| [backend/agents/metabolite_disease_agent.py](backend/agents/metabolite_disease_agent.py) | Called by `MasterAgent.run()` with the metabolite and disease. Returns a `HopEvidence` record. | Retrieves PubMed and CTD evidence for the metabolite–disease pair and chemical context from ChEBI. |
| [backend/agents/microbe_disease_agent.py](backend/agents/microbe_disease_agent.py) | Called by `MasterAgent.run()` with the microbe and disease. Returns a `HopEvidence` record. | Retrieves PubMed and Disbiome evidence for the microbe–disease pair. |
| [backend/agents/pubmed_query.py](backend/agents/pubmed_query.py) | Imported by all three pairwise agents to construct their searches and retrieve or reuse article counts. | Builds PubMed queries, expands entity names where available, and caches article counts. |
| [backend/agents/hop_evidence.py](backend/agents/hop_evidence.py) | Instantiated by each pairwise agent and serialized when `MasterAgent` assembles the evidence payload. | Defines the shared evidence record for one pairwise relationship, including its query, article count, database hits, and sources. |
| [backend/agents/evidence_aggregator.py](backend/agents/evidence_aggregator.py) | `MasterAgent` passes all three hop records to `aggregate()`. It takes the smaller of the microbe–metabolite and metabolite–disease article counts as the raw chain count. | Identifies the less-supported of those two links, retains all three article counts, and adds database support to calculate the agent’s novelty estimate. |

## Database and entity matching

| File | How it runs | Role |
| --- | --- | --- |
| [backend/db_checkers/__init__.py](backend/db_checkers/__init__.py) | Executed when Python imports the `db_checkers` package. | Exports the database lookup functions used by the agents. |
| [backend/db_checkers/bacdive_checker.py](backend/db_checkers/bacdive_checker.py) | Called by the microbe–metabolite agent. Reads `bacdive_edges.tsv` and reuses summaries for the same microbe. | Looks up microbial records in BacDive and summarizes the environments recorded for a matching microbe. |
| [backend/db_checkers/binded_checker.py](backend/db_checkers/binded_checker.py) | Called by the microbe–metabolite agent. Reads `binded_database_anno_named.csv` and looks up matching pairs. | Looks up microbial species and their reported compounds in BindedDB, retaining source and compound identifiers for matched pairs. |
| [backend/db_checkers/chebi_checker.py](backend/db_checkers/chebi_checker.py) | Called by the metabolite–disease agent. Searches `chebi_relationships_standardized.csv` for the metabolite. | Retrieves ChEBI chemical relationships matching a metabolite and returns related entities and relationship types. |
| [backend/db_checkers/ctd_checker.py](backend/db_checkers/ctd_checker.py) | Called by the metabolite–disease agent. Reads disease-matched rows from `CTD_chemicals_diseases.tsv`. | Matches chemical–disease records in the Comparative Toxicogenomics Database and summarizes the supporting records and relationship types. |
| [backend/db_checkers/disbiome_checker.py](backend/db_checkers/disbiome_checker.py) | Called by both microbe-focused agents. Searches `disbiome_edges.tsv` by microbe or by microbe and disease. | Retrieves Disbiome microbial records and tests for matching microbe–disease associations. |
| [backend/db_checkers/build_sapbert_index.py](backend/db_checkers/build_sapbert_index.py) | Run separately with `python backend/db_checkers/build_sapbert_index.py` after supplying the reference tables. Writes `entity_embeddings.npy` and `entity_mapping.json`. | Collects names and entity types from the reference tables and encodes each name into a searchable vector. |
| [backend/db_checkers/sapbert_retriever.py](backend/db_checkers/sapbert_retriever.py) | Imported by database checkers and synonym search helpers. Loads the index on demand and returns candidate names and similarity scores. | Searches the entity index using name matching and embedding similarity, with optional filtering by entity type. |

## R abundance and trajectory analysis

| File | How it runs | Role |
| --- | --- | --- |
| [r_pipeline/M1_targets_clr.R](r_pipeline/M1_targets_clr.R) | First `Rscript` call. Reads the staged abundance tables and writes `M1_cache.rds`. | Selects target microbes and metabolites, normalizes abundances, and prepares the centered log-ratio data used by later stages. |
| [r_pipeline/M2_root_select.R](r_pipeline/M2_root_select.R) | Second `Rscript` call. Reads the M1 cache and association tables and writes `roots/all_roots_noback.csv`. | Uses association statistics and metabolite abundances to select candidate roots for trajectory inference. |
| [r_pipeline/M3_pluscombno1.R](r_pipeline/M3_pluscombno1.R) | Third `Rscript` call. Reads the M1 cache and writes one `pluscomb/pluscombno1_<CAG>.csv` per target microbe. | Multiplies each metabolite’s transformed abundance by the target microbe’s transformed abundance within the same sample. |
| [r_pipeline/M4_trajectory.R](r_pipeline/M4_trajectory.R) | Fourth `Rscript` call. Reads the M1 cache, M2 roots, and M3 matrices and writes CSVs under `coords/`. | Runs dimensionality reduction, clustering, and trajectory inference to export coordinates and root-based pseudotime. With fewer than four metabolite rows, it orders them by summed absolute interaction values and exports one-dimensional coordinates. |
| [r_pipeline/trajectory_core/runtime.R](r_pipeline/trajectory_core/runtime.R) | Sourced by the Python worker’s `Rscript` dependency check and by M4 during trajectory analysis. | Checks package availability and defines the data structures and accessors used by the trajectory functions. |
| [r_pipeline/trajectory_core/settings.R](r_pipeline/trajectory_core/settings.R) | Sourced by `runtime.R` before the upstream trajectory functions are loaded. | Defines defaults used by the trajectory routines, including nearest-neighbor and dimensionality-reduction settings. |
| [r_pipeline/trajectory_core/upstream.R](r_pipeline/trajectory_core/upstream.R) | Sourced by `runtime.R`. M4 calls the trajectory functions through that runtime. | Contains the upstream R routines for dimensionality reduction, clustering, principal graph learning, and pseudotime ordering. |
| [r_pipeline/trajectory_core/packages.txt](r_pipeline/trajectory_core/packages.txt) | Used when preparing the R environment. `runtime.R` checks that its required packages are installed. | Names the R dependencies separately from the Python packages in `requirements.txt`. |
| [r_pipeline/trajectory_core/LICENSE](r_pipeline/trajectory_core/LICENSE) | Distributed with the trajectory core as its license notice. | Specifies the MIT terms and attribution for the bundled trajectory code. |
