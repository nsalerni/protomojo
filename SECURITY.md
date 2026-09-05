# Security policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately through
[protomojo security advisories](https://github.com/nsalerni/protomojo/security/advisories/new).
Do not include vulnerability details in a public issue. You should receive an
initial response within one week.

## Scope

protomojo parses untrusted Protocol Buffers binary data and proto3 JSON, then
generates Mojo code for proto3 schemas. The binary decoder rejects malformed
input and applies the protobuf reference nesting-depth limit. The JSON decoder
rejects malformed input and bounds nesting.

Proto2 schemas, Editions, and text format are out of scope. The project has
not had an external security review. Current reference results are in
[COMPLIANCE.md](COMPLIANCE.md).

## Residual risks

- The binary decoder rejects overlong 10-byte varints whose leftover high
  bits would overflow a 64-bit value, and rejects field number 0. Weekly
  mutation fuzz compares accept/reject with Python protobuf; remaining
  disagreements should be treated as bugs.
- The JSON decoder accepts a leading `+` only on quoted integers, matching
  Python `json_format`. Unquoted `+1` stays invalid JSON.
- Nesting and per-field size limits bound parser bombs; they do not replace
  application message-size policy (gRPC applies its own 4 MiB default).
