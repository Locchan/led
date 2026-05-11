# Clustering

If `cluster_members` is set at the top of the config file, the daemon spins
up a clustering subsystem in a separate thread. Each member exposes an
HTTPS endpoint and pings each other to detect outages; the master also
checks for version mismatches and master conflicts at startup.

All clustering state lives in `led/cluster.py`.

## Top-level config fields

| Field                            | Type            | Required | Default              | Description                                                                                              |
|----------------------------------|-----------------|----------|----------------------|----------------------------------------------------------------------------------------------------------|
| `cluster_members`                | object          | —        | —                    | `{name: "host:port"}` for every node in the cluster, including this one. Presence enables clustering.   |
| `cluster_port`                   | integer         | yes\*    | —                    | TCP port the cluster HTTPS server binds to.                                                              |
| `cluster_id`                     | string          | yes\*    | —                    | Shared secret. Sent as a SHA-256 hash in the `X-Cluster-Auth` header on every request.                   |
| `cluster_state_alert_target`     | string          | yes\*    | —                    | Instance ID of a configured target used for cluster alerts. Must exist; checked at startup.              |
| `cluster_master`                 | boolean         | no       | `false`              | If true, this node initiates pings to every other member.                                                |
| `cluster_member_down_alert_min`  | integer         | no       | `5`                  | Minutes of silence before a node is considered down and an alert fires. Alerts repeat hourly until up.   |
| `cluster_verify_tls`             | boolean         | no       | `true`               | Verify peer TLS certificates. Set to `false` if peers use auto-generated self-signed certs.              |
| `cluster_tls_dir`                | string          | no       | `/etc/led/tls`       | Directory holding `fullchain.pem` / `privkey.pem`. Layout matches letsencrypt's `live/<domain>/`.        |

\* required only when `cluster_members` is present.

Whenever an optional field is omitted, the daemon logs which default was
substituted. If `cluster_verify_tls` is `false`, a warning is logged on
every start.

## TLS certificates

On startup the daemon checks `cluster_tls_dir` for `fullchain.pem` and
`privkey.pem`. If either is missing, both are generated with `openssl`
(self-signed, RSA-2048, valid for ~74 years), and `cert.pem` / `chain.pem`
are also written so the layout matches letsencrypt's `live/<domain>/`. You
can replace the generated files with real letsencrypt certs at any time —
just point `cluster_tls_dir` at the live directory.

> Self-signed certs will fail verification by default. If you don't have
> real certs, set `cluster_verify_tls: false` on every node — the
> `X-Cluster-Auth` SHA-256 header is what actually authenticates requests.

## Endpoints

Every member runs:

- `GET /ping` → `{"ping": "pong"}`. The master calls this against each
  slave on a 60-second interval; slaves record the time of each incoming
  ping. Requires `X-Cluster-Auth`.
- `POST /handshake` with `{"version", "mode", "hostname", "cluster_id"}` →
  the responder returns the same shape. Each node sends one handshake to
  every other member at startup. Requires `X-Cluster-Auth`.

## Alerts

- **Node down**: when a node hasn't pinged (or been pinged) within
  `cluster_member_down_alert_min` minutes, the watcher emits
  `Lost communication with node '<name>'. Last successful ping was at '<time>'`.
  Repeats every hour until the node is reachable again.
- **Version mismatch** *(master only)*: at startup, if any peer reports a
  different `led` version than the master, an alert fires once.
- **Master conflict**: if a master sees any peer also reporting
  `mode: "master"` during the startup handshake, it emits
  `led: Refusing to start on <host>: there's another master in the cluster.`
  and exits with code 1.

## Example cluster section

```json
"cluster_members": {
  "node-a": "node-a.example:5500",
  "node-b": "node-b.example:5500"
},
"cluster_master": true,
"cluster_port": 5500,
"cluster_id": "shared-secret-string",
"cluster_state_alert_target": "alert_channel",
"cluster_verify_tls": false,
"cluster_member_down_alert_min": 5
```
