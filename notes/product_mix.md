# CTL product mix and value

Issue: #397. Branch: `issue-397-product-mix`.

## Changes

- `GroundSystemTree` carries sawlog and pulp volume from the reference stem logs.
- `GroundSystemResult.product_mix` aggregates `sawlog_m3` and `pulp_m3` into the
  run manifest/system summary.
- Tree Lab run KPIs include `product_mix`.
- Comparison page adds:
  - sawlog/pulp volumes,
  - sawlog/pulp price assumptions per side,
  - product revenue,
  - cost/m³ plus net margin,
  - revenue/margin bars and JSON export fields.

Default demo prices are project-level `system_args.sawlog_price_per_m3` and
`pulp_price_per_m3`, editable in the comparison assumptions panel.

## Verification

- Core test asserts aggregate product mix is populated.
- Comparison page JS syntax check and Studio tests pass.

## Limits

- Product prices are planning assumptions, not market contracts.
- Product classification comes from the reference stem model; it is not a
  mill-grade or log-quality model.
