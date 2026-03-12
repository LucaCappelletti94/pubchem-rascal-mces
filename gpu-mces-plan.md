# Plan: GPU-Accelerated MCES in Rust + CUDA

## Problem

Computing MCES (Maximum Common Edge Subgraph) similarity for all pairs of molecules in a dataset is embarrassingly parallel but CPU-bound. The massspecgym dataset (31K compounds, ~500M pairs) costs ~$300 and hours of wall time on a SLURM cluster. A single RTX 4090 could potentially do it in minutes.

## Why GPUs Fit This Problem

- Each pair comparison is **fully independent** — textbook data parallelism
- Molecules are tiny graphs: 10-70 heavy atoms, 10-100 bonds
- All intermediate data structures (product graphs, clique search stacks) fit in **shared memory** (~20 KB per pair)
- RTX 4090 has 16,384 CUDA cores — can process thousands of pairs simultaneously

## Algorithm (Per Pair)

The RASCAL algorithm for MCES:

1. **Build line graphs**: Transform each molecule (atoms + bonds) into its line graph (bonds become nodes, shared-atom bonds become edges)
2. **Build modular product graph**: Nodes = compatible bond pairs across the two molecules (matching atom types at both ends). Edges = consistent pairs (share atoms compatibly or are independent)
3. **Find maximum clique** in the product graph — this gives the MCES
4. **Compute similarity**: `2 * |MCES| / (|E1| + |E2|)`

Steps 1-2 are straightforward and parallel. Step 3 (max clique) is NP-hard in general but fast on these small, sparse product graphs.

## Memory Budget

| Data | Size | Where |
|------|------|-------|
| Per molecule (atoms + bonds + types) | ~500 bytes | Global memory |
| All 31,587 molecules | ~16 MB | Global memory |
| Product graph adjacency (bitset, typical) | ~15 KB | Shared memory |
| Clique search stack | ~5 KB | Shared memory |
| **Total per active pair** | **~20 KB** | Shared memory (48-100 KB available) |

## Throughput Estimate

| Scenario | Per-pair time | Throughput | Total for 500M pairs |
|----------|--------------|------------|---------------------|
| Optimistic | 0.01 ms | 1.6B pairs/sec | ~0.3 seconds |
| Realistic | 0.1 ms | 160M pairs/sec | ~3 seconds |
| Conservative | 1 ms | 16M pairs/sec | ~30 seconds |
| Pessimistic | 10 ms | 1.6M pairs/sec | ~5 minutes |

Even the pessimistic case is 100x faster than the CPU cluster, at zero marginal cost.

## Key Technical Challenges

### 1. Warp Divergence
Max-clique via Bron-Kerbosch has irregular branching. In SIMT, all 32 threads in a warp execute the same instruction — divergent branches serialize.

**Mitigations:**
- **Warp-per-pair**: All 32 threads in a warp cooperate on one pair (parallel neighbor checks, parallel candidate evaluation)
- **Sort pairs by difficulty**: Group molecules with similar edge counts so warps finish together
- **Timeout**: Cap per-pair compute; fall back to CPU for hard pairs

### 2. Shared Memory Overflow
Very large molecule pairs (100+ bonds each) can produce product graphs exceeding shared memory.

**Mitigations:**
- Spill to local/global memory for oversized pairs
- Or route them to CPU fallback (same timeout logic as current RASCAL)

### 3. No Recursion in Some GPU Backends
SPIR-V/Vulkan shaders don't support recursion. CUDA does (with stack limits).

**Mitigation:** Use iterative Bron-Kerbosch with explicit stack (better for GPU anyway).

## Toolchain Decision

### Recommended: Rust host + CUDA C kernel (Option C)

```
src/
  main.rs          # Host: load data, generate pairs, launch kernel, write output
  molecule.rs      # Compact molecule representation
  io.rs            # TSV/parquet I/O
kernels/
  mces.cu          # CUDA kernel: product graph + max clique
build.rs           # Compile .cu via cc crate + nvcc
```

**Why:** Full CUDA capability (shared memory, warp intrinsics, recursion). Mature toolchain. The kernel is the hard part and CUDA C is battle-tested for this.

### Alternative: Pure Rust-CUDA (Option A)

Using [Rust-CUDA](https://github.com/Rust-GPU/Rust-CUDA) to compile Rust directly to PTX. As of Aug 2025, this has matured significantly and supports compute capability target features. Worth trying — fall back to Option C if compiler issues arise.

### Not recommended: rust-gpu + wgpu (Option B)

No recursion in SPIR-V, and Vulkan compute shaders are more restrictive than CUDA. The irregular control flow of clique-finding doesn't map well.

## Data Flow

```
Python (RDKit)                    Rust + CUDA
─────────────                    ──────────────
SMILES → normalize → TSV    →    Load TSV
                                  Parse into compact graph repr
                                  Upload molecules to GPU
                                  Generate pair indices
                                  Launch MCES kernel (batched)
                                  Download similarity scores
                                  Write parquet output
```

Pre-processing stays in Python/RDKit (no need to reimplement cheminformatics). The Rust+CUDA code consumes the same TSV format as the existing pipeline and produces compatible parquet output.

## Phases

### Phase 1: CPU Reference (Rust)
- Implement MCES via product graph + iterative max clique in pure Rust
- Validate against RDKit RASCAL on known pairs
- Establish correctness baseline
- **Deliverable:** `cargo run -- --pairs pairs.tsv` outputs similarity scores

### Phase 2: Naive GPU Kernel
- One CUDA block per pair
- Iterative Bron-Kerbosch in shared memory
- No optimizations
- **Deliverable:** First GPU MCES benchmark vs CPU

### Phase 3: Optimized GPU Kernel
- Warp-cooperative clique search (32 threads per pair)
- Bitset adjacency representation in shared memory
- Sort pairs by estimated difficulty (product of edge counts)
- Timeout + CPU fallback for hard pairs
- Coalesced global memory reads for molecule data
- **Deliverable:** Optimized benchmark, profile with Nsight Compute

### Phase 4: Integration
- Read same TSV format as pubchem-rascal-mces
- Output compatible parquet (same schema: cid_a, cid_b, similarity, timed_out, compute_time_ms)
- Full end-to-end pipeline
- Validate: compare all similarity scores against CPU cluster results

## Dependencies

### Rust (host)
- `csv` — TSV parsing
- `arrow` / `parquet` — output format
- `cudarc` — CUDA driver API wrapper (launch kernels, manage memory)
- `clap` — CLI

### CUDA (kernel)
- nvcc (CUDA 13.0 on the target machine)
- Compiled via `cc` crate in `build.rs`

### Build
- `cmake` + `nvcc` (for CUDA compilation)
- Rust stable (if Option C) or nightly-2025-06-23 (if Option A)

## Testing Strategy

- **Ground truth:** RDKit RASCAL results from existing Python pipeline
- **Correctness:** Compare similarity scores within ±0.001 tolerance
- **Known edge cases:** identical molecules (1.0), completely different (0.0), timeout-prone large pairs
- **Benchmark pairs:** Sample 10K pairs across difficulty levels, measure GPU vs CPU time

## Development Machine

- **GPU:** NVIDIA RTX 4090 (16,384 CUDA cores, 24 GB VRAM, Ada Lovelace, compute capability 8.9)
- **CUDA:** 13.0, Driver 580.126.09
- **CPU:** AMD Threadripper PRO 5975WX (32c/64t) — for CPU reference baseline
- **RAM:** ~1 TB

## References

- [RASCAL algorithm (Raymond et al.)](https://greglandrum.github.io/rdkit-blog/posts/2023-11-08-introducingrascalmces.html) — original algorithm, RDKit implementation
- [Rust-CUDA](https://github.com/Rust-GPU/Rust-CUDA) — Rust → NVVM compiler backend
- [cudarc](https://github.com/coreylowman/cudarc) — Safe Rust wrappers for CUDA driver API
- [Jayaraj et al. 2016](https://ieeexplore.ieee.org/document/7529917) — GPU MCS via max-clique for drug discovery
- [Neural Graduated Assignment (2025)](https://arxiv.org/abs/2505.12325) — Neural MCES approximation (alternative approach)
- [SIGMo (SC'25)](https://github.com/antonio-decaro/SIGMo) — GPU subgraph isomorphism for molecules (related but different problem)
