# Harvester/forwarder role propagation

Issue: #363. Branch: `issue-363-forwarder-roles`.

## Problem

Studio allowed editing machine roles to `harvester`/`forwarder`, but derived
scenario machine CSVs kept the base roles. Runs completed, but replay labels
still showed feller-buncher/grapple-skidder, and core skidder validation rejected
a true `forwarder` scenario role.

## Changes

- Core skidder-equivalent roles now accept `forwarder`.
- `_ensure_derived_machines` updates roles for existing active machines, not just
  appending clone machines.
- Derived scenarios now carry harvester/forwarder roles into run machine metadata
  and replay labels.

## Verification

- Core test changes a skidder role to `forwarder` and runs.
- Studio test changes H1/H2/H3 roles and asserts the derived machines CSV.
- 36 targeted tests pass.

## Limits

Forwarders use the grapple-skidder cycle model in this reference implementation;
a forwarder-specific payload/cycle regression remains future work.
