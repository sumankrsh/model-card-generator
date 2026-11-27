# Model card: Store demand forecast (synthetic example)

A hand-written card of the kind teams keep in a wiki. `model-card check` reads
it as it is; it doesn't need to come from this tool.

## Overview

Forecasts weekly unit demand per store and product line for a made-up grocery
chain, used by replenishment planners to set order quantities.

## Intended use

Weekly replenishment planning for chilled and ambient lines. Planners can
override any forecast.

## Training data

Three years of weekly sales by store and product line, 2023 to 2025, from the
sales data mart.

## Validation data

The first 13 weeks of 2026, held out from training.

## Performance

Mean absolute percentage error 11.8% across all stores, 16.2% for stores
opened in the last year.

## Limitations

TBD

## Monitoring

Forecast error is reviewed in the weekly planning meeting; a store above 20%
error for three weeks is escalated to the forecasting team.

## Approvals

Signed off by the head of supply chain planning on 2026-02-10.
