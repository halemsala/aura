/* AURA eBPF stub — attach to TC/XDP in production with libbpf.
 * Extracts corner-line payload bytes into BPF_MAP_TYPE_RINGBUF.
 * This file is documentation + compile target; not loaded in sandbox.
 */
#include <linux/bpf.h>
/* SEC("xdp") int aura_corner_filter(struct xdp_md *ctx) { ... } */
