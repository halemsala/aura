# Hermes V10.2 QUANTUM (prático)

## Real vs marketing

| Claim do texto | Implementação real |
|----------------|-------------------|
| ZK + TPM | **Attestation por hash** de ficheiros críticos (`boot_attestation.sha256`) — não TPM hardware |
| Grok Arena 8 agentes | **Arena-lite**: ranking de candidatos de fix (regras + scores) |
| E2B Firecracker | Adapter opcional + **fallback local** |
| Event Bus | SQLite **WAL** + hash-chain + pub/sub sync |
| LCM | SQLite DAG de mensagens |
| HITL | Fila `hitl_queue/` fail-closed; `HERMES_HITL_AUTO=1` para lab |

## Uso
```bat
cd C:\aura\hermes_v10_quantum
hermes_v10_quantum.bat seal
hermes_v10_quantum.bat attest
hermes_v10_quantum.bat pipeline "arruma 404 matriz"
```

Paper-trade continua enforced.
