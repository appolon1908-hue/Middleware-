# Private proxy process recovery

## Observed incident

On Server A (`65.109.65.169`, SentinelX hostname `middleware`) at
2026-09-09T17:47:48Z, a passive process inventory counted 32,043 exited
`ssl_client` processes. The private Odoo proxy retained 16,022 zombie children
and the private n8n proxy retained 16,021. Each child still reported one seccomp
filter reference. Both containers had `HostConfig.Init=null` and no PID limit.
Their HTTPS wget health checks run every 30 seconds.

At 17:46:30Z, `/proc/vmallocinfo` showed 32,576 allocations labelled
`bpf_jit_alloc_exec` totalling 661,925,888 bytes, while `bpf_jit_limit` was
528,482,304. These labelled virtual allocations include allocator overhead and
are not the kernel's exact JIT charge. This evidence identifies unreaped proxy
children as a concrete contributor to filter retention; post-recovery readback
must establish whether releasing them resolves the observed errno 524 failures.
It does not establish a kernel version defect.

## Source correction

The two private proxy Compose definitions enable `init: true` so an init
process can adopt and reap orphaned health-check children. `pids_limit: 256`
bounds future process growth. TLS verification, read-only certificate mounts,
capability drops, no-new-privileges, private networks and lack of published host
ports are preserved. No image, application, database, workflow activation or
external-delivery configuration is changed by this patch.

Docker documents this process-reaping role for
[container init](https://docs.docker.com/engine/containers/multi-service_container/)
and [Compose init](https://docs.docker.com/reference/compose-file/services/#init).

## Bounded recovery and persistence

An authorized targeted restart of one affected stateless proxy at a time clears
its existing process namespace while retaining the same container configuration,
image, mounts and networks. Verify its identity, same pinned image and running
state before proceeding to the other proxy. Stop if it does not return; recover
that same container with its original configuration. The retired combined proxy
must remain stopped. No Docker daemon restart, reboot, kernel/sysctl change,
database operation or security-policy relaxation is part of this recovery.

A restart alone does not apply `init` or the PID limit. The durable fix requires
the protected infrastructure deployment authority to recreate only these two
services using the reviewed definitions and the exact deployed image digest.
The live checkout contains local changes and must not be reset or overwritten.
Do not use its source tag to select a different image during recovery. Preserve
the old rendered configuration and rollback image before recreation; use
service-scoped execution with no dependencies, builds or image pulls.

Acceptance requires the new containers to report `Init=true`, `PidsLimit=256`,
the expected image and unchanged security/network/mount configuration. Observe
multiple natural health-check intervals with no growing zombie count; check
that recent Middleware, Kong, Caddy and n8n health checks no longer report
seccomp errno 524. Re-run the protected backup validation and isolated restore
for the selected release/backup tuple before claiming deployment readiness.

Source tests and a successful proxy restart do not certify a production release.

## Offline regression check

```sh
python3 -m unittest discover -s tests -p test_internal_proxy_process_lifecycle.py -v
```

The init and process-limit checks fail for both pre-fix definitions. The suite
also verifies that the existing private TLS and container restrictions remain.
