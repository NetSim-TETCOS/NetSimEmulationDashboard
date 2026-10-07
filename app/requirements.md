# NetSim Online Emulation Demo Platform — Requirements Specification

## 1. Purpose

Build a web-based live demonstration platform for NetSim Emulator that allows remote participants to interact with a client dashboard from a browser while traffic is routed through a NetSim-based emulation path.

The platform must make the effects of NetSim-configured network behavior easy to observe in real time, including:

- Delay / latency
- Jitter
- Packet loss and retransmission effects
- Bandwidth constraints / congestion
- Temporary outages
- False Data Injection (FDI) / malformed or modified application data
- Recovery after network conditions return to normal

The system must support both:
1. A **Participant Dashboard** for remote attendees.
2. An **Instructor / Server Dashboard** for the presenter.

The platform should be designed as a reusable **NetSim Web Emulation Lab** rather than a one-off demo.

---

# 2. Current Network Context

## 2.1 Public Endpoint

A public DDNS hostname is available:

```text
netsimemulation.ddns.net
```

The current public test endpoint is:

```text
http://netsimemulation.ddns.net:8080
```

This endpoint has already been tested successfully from a phone using mobile data.

The NetSim host currently has LAN IP:

```text
192.168.0.49
```

A basic Python HTTP server on port 8080 has been successfully accessed:

- From another machine on the same LAN
- From an external mobile network via the DDNS hostname

## 2.2 Port 443 Constraint

TCP/UDP port 443 on the NetSim host is currently occupied by Windows Remote Desktop Services (`TermService`).

Therefore:

- The initial project must use port `8080` by default.
- The application must not assume port 443 is available.
- HTTPS support may be introduced later through a reverse proxy, alternative public port, or infrastructure change.

---

# 3. Project Goals

The application must:

1. Allow attendees to open one URL in a web browser with no special software installation.
2. Allow each attendee to become a live network endpoint for NetSim demonstrations.
3. Show understandable metrics in real time.
4. Allow the instructor to see all connected clients.
5. Support browser-based round-trip latency testing.
6. Support server-initiated probes.
7. Support text message / echo testing.
8. Support continuous telemetry data streams.
9. Make NetSim-induced changes visible through charts and statistics.
10. Allow the instructor to mark or annotate network-change events.
11. Support controlled FDI / malformed-message demonstrations.
12. Record time-series data for later analysis.
13. Remain visually simple enough for training sessions and FDPs.
14. Be modular enough to add future experiments later.

---

# 4. Primary Users

## 4.1 Participant

A participant is a remote attendee accessing the application using a web browser.

Participant capabilities:

- Join a session
- Receive a generated participant ID
- Optionally enter a display name / institution
- See connection status
- Run browser-safe ping / latency tests
- Send messages to the server
- Receive echoed messages
- View live telemetry
- Observe delay, jitter, timeouts, and anomalies
- See charts updating live
- See experiment state changes
- See application-level anomalies caused by FDI

## 4.2 Instructor

The instructor operates the server side and controls the session.

Instructor capabilities:

- See all connected clients
- See per-client statistics
- See aggregate session metrics
- Start / stop experiment modes
- Start server-originated probes
- Enable / disable telemetry streams
- Mark experiment transitions
- Select or label the current NetSim condition
- Observe baseline versus current metrics
- View FDI-related differences
- Disconnect clients if necessary
- Export session data

---

# 5. Technology Recommendations

## 5.1 Backend

Preferred:

```text
Python 3.12+
FastAPI
Uvicorn
WebSockets
Pydantic
SQLite for initial persistence
```

Alternative:

```text
Node.js + Express + WebSocket / Socket.IO
```

Preferred implementation for initial version: **FastAPI + WebSockets**.

## 5.2 Frontend

Preferred:

```text
HTML5
CSS3
JavaScript / TypeScript
React or lightweight vanilla JS
Chart.js or Apache ECharts
```

Recommended initial implementation:

```text
React + TypeScript + Vite
```

If rapid prototyping is preferred:

```text
HTML + JavaScript + Chart.js
```

## 5.3 Communication

Use:

- WebSocket for live bidirectional communication
- HTTP REST APIs for configuration and session state
- JSON payloads for application messages

## 5.4 Persistence

Initial version:

```text
SQLite
```

Future option:

```text
PostgreSQL
```

---

# 6. High-Level Architecture

```text
Remote Participant Browser
        |
        | HTTP / WebSocket
        v
netsimemulation.ddns.net:8080
        |
        v
Public/NAT Forwarding
        |
        v
NetSim Host / Gateway
        |
        +----------------------+
        | Web Frontend        |
        | FastAPI Backend     |
        +----------------------+
        |
        | Experiment Traffic
        v
NetSim Emulated Path
        |
        v
Application Backend / Test Service
```

The software must be structured so the web application can later be split into:

```text
Public frontend/gateway
        |
        v
NetSim
        |
        v
Backend application server
```

This separation will make NetSim truly inline between client-side and application-side traffic.

---

# 7. Functional Requirements

## 7.1 Session Management

The platform must support live demo sessions.

Each session shall contain:

- Session ID
- Session name
- Start time
- End time
- Instructor identity
- Connected participant count
- Current experiment mode
- Notes / event markers

Example:

```json
{
  "session_id": "session-2026-09-30-001",
  "name": "NetSim Online Emulation Demo",
  "status": "active",
  "experiment": "baseline"
}
```

## 7.2 Participant Registration

When a participant opens the site:

1. Generate a unique participant ID.
2. Display the ID prominently.
3. Ask optionally for:
   - Name
   - Institution
4. Store:
   - Connection time
   - Browser
   - OS
   - Public/observed IP where available
   - Session ID
   - User agent
5. Mark the client as online.

Example participant ID:

```text
P001
P002
P003
...
```

## 7.3 Connection Status

Participant UI must show:

- Connected / disconnected state
- Session ID
- Server reachability
- WebSocket state
- Last successful heartbeat

Example:

```text
Connection: CONNECTED
Server: ONLINE
Last response: 120 ms ago
```

## 7.4 Browser-Safe Ping / Latency Test

Since normal browser JavaScript cannot send ICMP Echo directly, implement a WebSocket/HTTP application-level probe.

Flow:

```text
Client -> PING(seq, timestamp)
Server -> PONG(seq, timestamp)
Client computes RTT
```

The client shall support:

- Start probe
- Stop probe
- Configurable interval:
  - 500 ms
  - 1 second
  - 2 seconds
  - 5 seconds
- Probe sequence number
- RTT calculation
- Timeout detection

Metrics:

- Current RTT
- Minimum RTT
- Maximum RTT
- Average RTT
- Median RTT
- Jitter
- Timeout count
- Success count
- Probe success percentage

## 7.5 Jitter Calculation

Use a clearly documented formula.

Recommended initial implementation:

```text
jitter = average absolute difference between consecutive RTT samples
```

The UI must label this as:

```text
Observed RTT Jitter
```

## 7.6 Baseline Latency

Each participant must have a baseline measurement.

Baseline procedure:

- Automatically collect first N valid RTT samples
- Recommended N = 10
- Calculate baseline average and median

Then show:

```text
Baseline RTT: 38 ms
Current RTT: 243 ms
Change: +205 ms
```

This is important because online attendees will have different Internet-path delays.

## 7.7 Server-Initiated Probe

The instructor/server shall be able to initiate a probe toward a client over WebSocket.

Flow:

```text
Server -> PROBE(seq, timestamp)
Client -> PROBE_ACK(seq)
Server calculates round-trip time
```

This allows:

- Participant-measured RTT
- Server-measured RTT

Both should be visible independently.

## 7.8 Optional True ICMP Test

Add a future-capable backend module for true ICMP ping.

Requirements:

- Disabled by default
- Server-side only
- Only possible toward reachable client IPs
- Must not be assumed to work through NAT
- UI must clearly label the distinction:

```text
Application Probe
ICMP Ping
```

The application must never mislabel application-level latency as ICMP latency.

---

# 8. Message / Echo Experiment

## 8.1 Participant Message UI

Participant shall have a text box:

```text
[ Type message here... ]
[ SEND ]
```

On send, record:

- Message ID
- Client ID
- Send timestamp
- Server receive timestamp
- Server echo timestamp
- Client receive timestamp
- Round-trip delivery time

## 8.2 Echo Mode

Server shall echo the received message.

Participant UI shall display:

```text
Original message
Echoed message
Round-trip time
Status
```

## 8.3 Malformed / FDI-Aware Payload

Support structured messages.

Example:

```json
{
  "type": "telemetry",
  "sequence": 1024,
  "sensor_id": "TEMP-01",
  "value": 26.4,
  "unit": "C"
}
```

The payload format should be deterministic and easy for NetSim-side logic to inspect or modify.

---

# 9. Telemetry Experiment

## 9.1 Telemetry Stream

Server shall generate one or more telemetry streams.

Default example:

```json
{
  "sequence": 1001,
  "timestamp": 1790750100000,
  "vehicle_id": "V21",
  "speed": 42,
  "temperature": 26.4,
  "brake_status": false
}
```

Default stream interval:

```text
1 message / second
```

Instructor should be able to select:

- 0.5 sec
- 1 sec
- 2 sec
- 5 sec

## 9.2 Participant Telemetry View

Show cards:

```text
Vehicle Speed
42 km/h

Temperature
26.4 °C

Brake
OFF
```

Show:

- Last update age
- Sequence number
- Missing sequence count
- Suspicious values
- Last 20 telemetry records

## 9.3 Telemetry Validation

Implement configurable expected ranges.

Example:

```text
Vehicle speed:
0 to 120 km/h

Temperature:
-20 to 80 °C
```

If received data exceeds the configured range:

```text
ANOMALY DETECTED
```

Do not automatically claim the anomaly is malicious unless the instructor explicitly marks FDI mode.

---

# 10. False Data Injection Demonstration

## 10.1 Purpose

Demonstrate how application data may be modified while traversing the emulated network.

## 10.2 Requirements

The application protocol must use predictable structured fields.

Example original:

```json
{
  "speed": 48
}
```

Example received after manipulation:

```json
{
  "speed": 148
}
```

## 10.3 Participant Display

Show:

```text
Vehicle Speed
148 km/h
Warning: outside expected range
```

## 10.4 Instructor Display

Where available, the instructor should see:

```text
Server generated: 48 km/h
Client reported: 148 km/h
Difference: +100 km/h
```

This requires the client to send a receipt/acknowledgement with the data it actually received.

Example:

```json
{
  "type": "telemetry_receipt",
  "sequence": 1001,
  "received_value": 148
}
```

## 10.5 Integrity Metadata

Optionally include:

```text
message_id
sequence
original_hash
received_hash
```

Hash validation may be used to demonstrate integrity failure.

---

# 11. Participant Dashboard Requirements

## 11.1 Header

Show:

- NetSim Live Network Lab
- Participant ID
- Optional participant name
- Connection status
- Session status

## 11.2 Summary Cards

Minimum cards:

```text
Current RTT
Baseline RTT
Latency Change
Jitter
Timeout Rate
Message Count
```

## 11.3 Latency Plot

Real-time line chart.

Requirements:

- X-axis = time
- Y-axis = RTT ms
- Rolling 60-second default view
- Keep configurable history up to 10 minutes
- Show experiment markers
- Show baseline reference line

## 11.4 RTT Statistics Panel

Show:

```text
Current
Min
Average
Median
Max
Jitter
P95
```

P95 may be placed under an advanced section if the participant view becomes too technical.

## 11.5 Probe Controls

Buttons:

```text
START LATENCY TEST
STOP
RESET
```

Interval selector.

## 11.6 Message Panel

Include:

- Text input
- Send button
- Last server response
- Delivery time
- Message history

## 11.7 Telemetry Panel

Include:

- Live cards
- Latest values
- Sequence number
- Update age
- anomaly state

## 11.8 Event Log

Participant-friendly event stream:

```text
12:04:01 Connected
12:04:15 Baseline completed
12:05:03 Network condition changed
12:05:21 Latency increased
12:07:44 Telemetry anomaly detected
```

---

# 12. Instructor Dashboard Requirements

## 12.1 Session Summary

Show:

```text
Connected Participants
Active Probes
Messages / Minute
Median RTT
P95 RTT
Average Jitter
Timeout Rate
```

## 12.2 Participant Table

Columns:

```text
ID
Name
Institution
IP
Connection State
Current RTT
Baseline RTT
RTT Delta
Jitter
Timeout %
Messages
Last Activity
```

Must support:

- Sorting
- Filtering
- Search
- Row click for detail
- Automatic refresh

## 12.3 Participant Detail Drawer/Page

Show:

```text
Participant ID
Name
Institution
Browser
OS
IP
Connection start
Session duration
Last activity
```

Metrics:

```text
Current RTT
Baseline RTT
Average RTT
Median RTT
Min RTT
Max RTT
P95 RTT
Jitter
Probe count
Timeout count
Message count
Telemetry records
```

Charts:

- RTT over time
- jitter over time
- probe success over time

## 12.4 Aggregate RTT Plot

Line chart containing:

- Median RTT across connected clients
- P95 RTT
- Optional mean RTT

Experiment markers must appear as vertical annotations.

## 12.5 Client Comparison Chart

Bar chart:

```text
Participant vs Current RTT
```

Optional tabs:

```text
RTT
Jitter
Timeout %
```

## 12.6 Connected Client Trend

Chart connected clients over time.

## 12.7 Global Event Log

Instructor shall see:

```text
Participant joined
Participant left
Experiment started
Experiment changed
FDI marker added
Outage started
Outage ended
```

---

# 13. Experiment Control Model

The web application does not directly need to control NetSim in version 1.

Instead, the instructor shall label the current experiment state manually.

Experiment states:

```text
BASELINE
DELAY
JITTER
LOSS
CONGESTION
OUTAGE
FDI
RECOVERY
CUSTOM
```

Instructor UI:

```text
Current Experiment:
[ BASELINE v ]

[ APPLY LABEL ]
```

Optional notes:

```text
NetSim configured with 100 ms one-way delay
```

The selected experiment state shall be pushed to all connected clients.

---

# 14. Event Markers

Instructor must be able to add event markers.

Example:

```text
12:15:30 Delay changed to 100 ms
12:17:05 Loss configured to 5%
12:18:40 FDI enabled
12:20:10 Normal network restored
```

These markers must:

- Appear in instructor charts
- Appear in participant charts
- Be saved in session history
- Be exportable

---

# 15. Baseline vs Current Analytics

For each participant calculate:

```text
RTT delta = current RTT - baseline RTT
RTT increase % = ((current - baseline) / baseline) * 100
```

Show:

```text
Baseline RTT: 42 ms
Current RTT: 246 ms
Added observed delay: +204 ms
```

The phrase **Observed RTT Increase** is preferred over directly claiming:

```text
NetSim-added delay
```

unless the experiment topology guarantees this exactly.

---

# 16. Packet Loss Interpretation

Because WebSocket runs over TCP:

Packet loss at the IP layer may appear as:

- Increased RTT
- Temporary stall
- Retransmission
- Reduced throughput
- Increased jitter

The participant UI should not claim:

```text
WebSocket message lost
```

unless the application genuinely detects a missing application-level message.

For telemetry:

Use sequence numbers to detect:

```text
late
duplicate
out-of-order
missing
```

records.

---

# 17. WebSocket Message Types

Recommended protocol.

## 17.1 Client -> Server

### `client_hello`

```json
{
  "type": "client_hello",
  "name": "Kanak",
  "institution": "TETCOS"
}
```

### `ping`

```json
{
  "type": "ping",
  "sequence": 101,
  "client_timestamp": 1790750100123
}
```

### `probe_ack`

```json
{
  "type": "probe_ack",
  "sequence": 201
}
```

### `message_send`

```json
{
  "type": "message_send",
  "message_id": "m-101",
  "text": "Hello server"
}
```

### `telemetry_receipt`

```json
{
  "type": "telemetry_receipt",
  "sequence": 1001,
  "received_payload": {
    "speed": 148
  }
}
```

### `heartbeat`

```json
{
  "type": "heartbeat"
}
```

## 17.2 Server -> Client

### `welcome`

```json
{
  "type": "welcome",
  "client_id": "P017",
  "session_id": "session-001"
}
```

### `pong`

```json
{
  "type": "pong",
  "sequence": 101,
  "client_timestamp": 1790750100123,
  "server_timestamp": 1790750100243
}
```

### `server_probe`

```json
{
  "type": "server_probe",
  "sequence": 201,
  "server_timestamp": 1790750101000
}
```

### `message_echo`

```json
{
  "type": "message_echo",
  "message_id": "m-101",
  "text": "Hello server"
}
```

### `telemetry`

```json
{
  "type": "telemetry",
  "sequence": 1001,
  "server_timestamp": 1790750102000,
  "speed": 42,
  "temperature": 26.4
}
```

### `experiment_state`

```json
{
  "type": "experiment_state",
  "mode": "DELAY",
  "label": "100 ms one-way delay",
  "timestamp": 1790750103000
}
```

### `event_marker`

```json
{
  "type": "event_marker",
  "label": "Packet loss set to 5%",
  "timestamp": 1790750104000
}
```

---

# 18. REST API Requirements

Suggested endpoints.

## Session

```text
POST   /api/session/start
POST   /api/session/stop
GET    /api/session/current
GET    /api/session/{id}
```

## Participants

```text
GET    /api/participants
GET    /api/participants/{client_id}
DELETE /api/participants/{client_id}
```

## Experiments

```text
GET    /api/experiment
POST   /api/experiment
POST   /api/experiment/marker
```

## Metrics

```text
GET    /api/metrics/summary
GET    /api/metrics/client/{client_id}
GET    /api/metrics/session/{session_id}
```

## Export

```text
GET    /api/export/session/{session_id}.json
GET    /api/export/session/{session_id}.csv
```

---

# 19. Data Models

## 19.1 Participant

```text
id
session_id
display_name
institution
ip_address
user_agent
browser
os
connected_at
disconnected_at
last_seen
status
baseline_rtt
```

## 19.2 Probe Sample

```text
id
session_id
client_id
sequence
direction
sent_at
received_at
rtt_ms
status
```

Direction:

```text
client_to_server
server_to_client
```

## 19.3 Message Record

```text
id
session_id
client_id
message_id
original_text
received_text
sent_at
server_received_at
client_received_at
rtt_ms
```

## 19.4 Telemetry Record

```text
id
session_id
client_id
sequence
server_generated_payload
client_received_payload
server_timestamp
client_receipt_timestamp
is_anomalous
```

## 19.5 Event Marker

```text
id
session_id
timestamp
event_type
label
notes
```

---

# 20. Metrics Calculation

Per-client:

```text
current_rtt
min_rtt
max_rtt
mean_rtt
median_rtt
p95_rtt
jitter
success_count
timeout_count
timeout_percentage
baseline_rtt
rtt_delta
```

Aggregate:

```text
connected_clients
median_client_rtt
mean_client_rtt
p95_client_rtt
average_jitter
total_messages
messages_per_minute
total_timeouts
timeout_percentage
```

---

# 21. Timeout Logic

Default probe timeout:

```text
5 seconds
```

Must be configurable.

A probe shall be marked:

```text
pending
success
timeout
```

Late replies should be:

```text
late
```

rather than silently discarded.

---

# 22. Reconnection Handling

WebSocket clients must reconnect automatically.

Requirements:

- Exponential backoff
- Maximum backoff around 10 seconds
- Preserve participant ID in browser local storage
- Attempt to restore previous session identity
- Mark temporary disconnects
- Do not create a new participant every few seconds during unstable links

---

# 23. Browser Storage

Use local storage for:

```text
participant_id
participant_name
institution
last_session_id
```

Do not store sensitive credentials in local storage.

---

# 24. UI / UX Requirements

## 24.1 General Style

Modern, professional, technical, presentation-friendly.

Design goals:

- Clear
- High contrast
- Large numbers
- Minimal clutter
- Suitable for projector display
- Suitable for laptop and mobile browsers

## 24.2 Status Indicators

Use semantic states:

```text
Connected
Disconnected
Normal
Degraded
Anomaly
Timeout
```

Avoid overcomplicated technical jargon on participant view.

## 24.3 Responsive Design

Must work on:

- Desktop
- Laptop
- Tablet
- Mobile

Participant dashboard should remain fully usable on a phone.

---

# 25. Dashboard Navigation

Participant navigation:

```text
Overview
Latency Test
Messages
Telemetry
Events
```

Instructor navigation:

```text
Overview
Participants
Latency
Messages
Telemetry
Experiments
Events
Export
```

---

# 26. Chart Requirements

Use a chart library supporting live updates.

Minimum charts:

Participant:
1. RTT over time
2. Optional RTT distribution
3. Optional telemetry history

Instructor:
1. Median RTT over time
2. P95 RTT over time
3. Participant RTT comparison
4. Jitter over time
5. Connected participants over time
6. Timeout rate over time

Charts must support:

- Real-time update
- Tooltips
- Legends
- Event markers
- Pause
- Reset
- Rolling time windows

---

# 27. Suggested Demo Status Categories

Configurable demo thresholds:

```text
Excellent: < 50 ms
Good:      50 - 100 ms
Degraded:  100 - 250 ms
Poor:      > 250 ms
```

These must be clearly marked as:

```text
Demo thresholds
```

They are not universal networking standards.

---

# 28. Logging Requirements

Server logs shall include:

```text
timestamp
client_id
event
remote_ip
session_id
message_type
latency where relevant
```

Log levels:

```text
INFO
WARNING
ERROR
DEBUG
```

Do not log sensitive message contents by default.

---

# 29. Security Requirements

## 29.1 Initial Version

The service is public-facing.

Minimum requirements:

- Do not expose directory listings
- Serve only application files
- Validate all incoming JSON
- Limit message size
- Rate-limit repeated requests
- Sanitize user-provided names and messages
- Prevent script injection
- Prevent arbitrary file access
- Disable debug stack traces in production
- CORS restricted appropriately
- Origin validation for WebSocket connections

## 29.2 Admin Authentication

Instructor dashboard must eventually require authentication.

Initial development mode may support:

```text
ADMIN_TOKEN environment variable
```

Production should support proper authentication.

## 29.3 Rate Limiting

Recommended defaults:

```text
Probe messages: max 10 / sec / client
Text messages: max 5 / sec / client
Registration attempts: max 10 / min / IP
```

---

# 30. Configuration

Use environment variables.

Example `.env`:

```text
HOST=0.0.0.0
PORT=8080

PUBLIC_HOST=netsimemulation.ddns.net

PROBE_INTERVAL_MS=1000
PROBE_TIMEOUT_MS=5000

TELEMETRY_INTERVAL_MS=1000

SESSION_NAME=NetSim Online Emulation Demo

ADMIN_TOKEN=change-me

DATABASE_URL=sqlite:///./netsim_demo.db
```

Provide:

```text
.env.example
```

Do not commit secrets.

---

# 31. Deployment Requirements

Initial deployment target:

```text
Windows PC
192.168.0.49
```

Public:

```text
netsimemulation.ddns.net:8080
```

The project must include a simple Windows startup command.

Example:

```bat
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Provide:

```text
start_server.bat
```

Optional:

```text
stop_server.bat
```

---

# 32. Suggested Project Structure

```text
netsim-web-emulation/
|
+-- backend/
|   +-- app/
|   |   +-- main.py
|   |   +-- config.py
|   |   +-- models.py
|   |   +-- database.py
|   |   +-- websocket_manager.py
|   |   +-- metrics.py
|   |   +-- telemetry.py
|   |   +-- sessions.py
|   |   +-- routers/
|   |       +-- session.py
|   |       +-- participants.py
|   |       +-- metrics.py
|   |       +-- experiment.py
|   |
|   +-- tests/
|
+-- frontend/
|   +-- src/
|   |   +-- participant/
|   |   +-- instructor/
|   |   +-- components/
|   |   +-- charts/
|   |   +-- services/
|   |   +-- types/
|   |
|   +-- public/
|
+-- scripts/
|   +-- start_server.bat
|
+-- docs/
|
+-- .env.example
+-- requirements.md
+-- README.md
+-- requirements.txt
```

---

# 33. Testing Requirements

## 33.1 Unit Tests

Test:

- RTT calculations
- Median
- P95
- Jitter
- Timeout handling
- Participant registration
- Session state
- Telemetry validation
- Event markers

## 33.2 Integration Tests

Test:

- WebSocket connect
- Ping/pong
- Reconnect
- Server probe
- Message echo
- Telemetry
- Multiple clients
- Session start/stop

## 33.3 Load Test

Initial target:

```text
100 simultaneous participants
```

Stretch target:

```text
250 simultaneous participants
```

Test:

- 1 probe/sec/client
- 1 telemetry message/sec/client
- dashboard responsiveness

## 33.4 External Connectivity Test

Verify:

```text
http://netsimemulation.ddns.net:8080
```

from:

- Mobile data
- External broadband connection
- At least one remote geographic location if practical

---

# 34. Performance Targets

Initial target:

```text
100 connected WebSocket clients
```

Server CPU usage should remain reasonable.

Metrics updates to instructor dashboard:

```text
1 update per second
```

Participant graph updates:

```text
1 sample per second
```

Do not redraw the entire chart history on every update if avoidable.

---

# 35. Reliability Requirements

The application must:

- Survive individual client disconnects
- Automatically clean stale sessions
- Prevent one bad client from crashing the server
- Handle malformed JSON safely
- Handle network interruption gracefully
- Continue serving existing clients when one participant reconnects

---

# 36. Privacy Requirements

The interface must not expose one participant's IP address to other participants.

Participant view may show only:

```text
Participant ID
own metrics
own messages
shared experiment state
```

Instructor may see client IP addresses.

---

# 37. Phase 1 MVP

Build first:

1. FastAPI server
2. Participant registration
3. Participant dashboard
4. Instructor dashboard
5. WebSocket connection
6. Browser-safe ping
7. Live RTT chart
8. Min/avg/max/median
9. Baseline RTT
10. Instructor client table
11. Aggregate RTT view
12. Message echo
13. Manual experiment labels
14. Event markers
15. SQLite persistence

Acceptance:

- External participant connects through DDNS endpoint
- Instructor sees participant
- Participant starts ping
- RTT updates live
- Instructor sees same client's RTT
- Changing network conditions produces visible RTT changes

---

# 38. Phase 2

Add:

1. Telemetry stream
2. Telemetry charts
3. Anomaly detection
4. FDI receipt comparison
5. Server-initiated probes
6. CSV/JSON export
7. Session replay
8. Better authentication
9. Improved responsive UI

---

# 39. Phase 3

Add:

1. Throughput / file-transfer experiment
2. Controlled download test
3. Controlled upload test
4. UDP-based experiment if architecture permits
5. WebRTC data-channel experiment
6. Network outage visualization
7. Automatic experiment-state integration with NetSim if API/hooks become available
8. Experiment templates:
   - Wi-Fi
   - 5G
   - NTN
   - IoT
   - VANET
   - UWAN

---

# 40. Future Enhancements

Potential additions:

- Live packet counter
- Throughput chart
- Loss/retransmission visualization
- Video stream demo
- Audio quality demo
- Multi-server topology
- Participant grouping
- Geographic participant map
- Session recording
- PDF report generation
- QR code join page
- Instructor-controlled announcement banner
- Quiz mode
- Multiple simultaneous experiments
- Direct integration with NetSim parameter control
- Automatic NetSim scenario synchronization

---

# 41. Key Design Principle

The application must be a **measurement and visualization layer**, not just a webpage.

The participant should visibly experience:

```text
Normal network
        |
        v
NetSim condition changes
        |
        v
Observed application behavior changes
```

The instructor should simultaneously see:

```text
All participants
+
Per-client metrics
+
Aggregate metrics
+
Experiment timeline
```

The platform must help explain the relationship between:

```text
Network impairment
        ↓
Transport behavior
        ↓
Application behavior
        ↓
User experience
```

---

# 42. Important Networking Notes

1. Browser-based ping is not true ICMP.
2. WebSocket uses TCP.
3. IP packet loss may appear as retransmission delay rather than missing WebSocket messages.
4. Public Internet RTT differs by participant.
5. Baseline-versus-current comparison is essential.
6. Client and server clocks are not assumed synchronized.
7. RTT is more reliable than direct one-way latency calculation.
8. True one-way delay should not be claimed unless clocks are synchronized.
9. DDNS does not hide the public IP; it provides a stable hostname.
10. HTTPS is not part of the initial MVP because port 443 is currently occupied by Remote Desktop Services.

---

# 43. Codex Implementation Instructions

Codex should:

1. Create a clean repository using the recommended project structure.
2. Build the MVP first.
3. Keep backend and frontend modular.
4. Add detailed inline comments only where useful.
5. Use type-safe models.
6. Use async WebSocket handling.
7. Avoid blocking operations in request handlers.
8. Include automated tests.
9. Include `README.md`.
10. Include `.env.example`.
11. Include a Windows startup script.
12. Make all key intervals configurable.
13. Do not hard-code `192.168.0.49` unless used as a documented example.
14. Do not hard-code DDNS hostname except via configuration.
15. Use `netsimemulation.ddns.net` as the default example public hostname.
16. Start on port `8080`.
17. Ensure the instructor dashboard and participant dashboard are separate routes.

Suggested routes:

```text
/
Participant dashboard

/instructor
Instructor dashboard

/api/...
REST API

/ws
WebSocket endpoint
```

---

# 44. MVP Acceptance Checklist

The MVP is complete when all of the following are true:

- [ ] Server starts on Windows using one command.
- [ ] Server listens on `0.0.0.0:8080`.
- [ ] Participant can open the public DDNS URL.
- [ ] Participant receives a unique ID.
- [ ] Instructor dashboard shows the participant.
- [ ] Participant can start and stop latency probing.
- [ ] RTT updates at approximately 1-second intervals.
- [ ] Participant sees current/min/avg/max/median RTT.
- [ ] Baseline RTT is calculated automatically.
- [ ] Participant sees baseline versus current RTT.
- [ ] Instructor sees all participant RTT values.
- [ ] Instructor sees aggregate median RTT.
- [ ] Participant can send a message.
- [ ] Server echoes the message.
- [ ] Message round-trip time is shown.
- [ ] Instructor can set experiment mode.
- [ ] Participants receive experiment-mode updates.
- [ ] Instructor can create event markers.
- [ ] Event markers appear on charts.
- [ ] Data is persisted in SQLite.
- [ ] Session data can be exported to JSON.
- [ ] Application handles client disconnect/reconnect.
- [ ] UI works on desktop and mobile.
- [ ] Application does not expose arbitrary filesystem contents.
- [ ] Application remains stable with at least 100 simulated concurrent clients.

---

# 45. Initial Demonstration Flow

The first end-to-end demo should work like this:

1. Instructor starts application.
2. Participant opens:

```text
http://netsimemulation.ddns.net:8080
```

3. Participant receives:

```text
Participant P017
Connected
```

4. Participant clicks:

```text
START LATENCY TEST
```

5. Dashboard shows:

```text
Baseline RTT: 42 ms
Current RTT: 44 ms
Jitter: 3 ms
```

6. Instructor changes NetSim to introduce delay.
7. Participant sees:

```text
Current RTT: 244 ms
Observed increase: +202 ms
```

8. Instructor applies an event marker:

```text
100 ms one-way delay enabled
```

9. Marker appears on both dashboards.
10. Instructor introduces loss/congestion.
11. Participant sees increased jitter and stalls/timeouts.
12. Instructor enables telemetry.
13. Participant sees live data.
14. Instructor performs FDI through NetSim.
15. Participant sees abnormal data.
16. Instructor dashboard shows expected vs client-received values where possible.
17. NetSim is restored to normal.
18. RTT returns toward baseline.
19. Session is exported.

This flow is the primary success scenario for the project.
