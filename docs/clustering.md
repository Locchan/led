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
| `cluster_connectivity_skip`        | object            | no         | `{}`                   | Per-member daily windows when that peer is not checked. Values are `HH:MM:minutes` lists. See below.       |

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

All alerts (cluster or otherwise) are routed through `led.alerts.send_alert`
and wrapped in a consistent envelope before being passed to the target:

```
led alert from <node_name>:
<message>
```

`<node_name>` is the cluster member name when the node has self-identified
in `cluster_members`, otherwise `socket.gethostname()`.

Cluster-specific alert messages:

- **Node down**: when a node hasn't pinged (or been pinged) within
  `cluster_member_down_alert_min` minutes, the watcher emits
  `Lost communication with node '<name>'. Last successful ping was at '<time>'`.
  Repeats every hour until the node is reachable again. When the connection
  comes back, one alert reports
  `Connection to node '<name>' reestablished. Total downtime was <duration>.`
  Downtime runs from the last successful ping until the connection returns.
  Silence inside that peer's `cluster_connectivity_skip` window does not count
  toward this threshold and does not produce a reestablished alert.
- **Version mismatch** *(master only)*: at startup, if any peer reports a
  different `led` version than the master, an alert fires once.
- **Master conflict**: if a master sees any peer also reporting
  `mode: "master"` during the startup handshake, it emits
  `Refusing to start on <host>: there's another master in the cluster.`
  and exits with code 1.

## Connectivity skip periods

`cluster_connectivity_skip` names the members this node will not check
during a daily window. Other members are still checked. Each value is a
list of `HH:MM:minutes` strings:

- `HH:MM` is the local start time, 24-hour and zero-padded (`03:55`).
- `minutes` is how long checks against that member stay off.

`"03:55:10"` skips that member from 03:55 until 04:05. A window may cross
midnight: `"23:00:120"` is 23:00–01:00. A duration of 1440 minutes or more
skips that member for the whole day.

On the master, a window means "do not ping this member." On that member,
name the master and use the same window so it does not treat the missing
pings as an outage. When a window ends, that peer's last-ping time is
reset, so the gap does not immediately raise a node-down alert.

```json
"cluster_connectivity_skip": {
  "node-b": ["03:55:10"]
}
```

The same object on node-b names the master (`"node-a": ["03:55:10"]`).
Windows are evaluated on the watcher's 60-second tick.

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
"cluster_member_down_alert_min": 5,
"cluster_connectivity_skip": {
  "node-b": ["03:55:10"]
}
```
