# DSN allocator: before vs after

Same simulation, telemetry and link assumptions for both methods. 2020 windows are not confirmed DSN availability.

| Case | Method | Contacts | Sats without contact | Reserved h | Delivered Mbit | Max peak memory Mbit | Sats with deadline violation |
|---|---|---:|---|---:|---:|---:|---:|
| pipeline_2020_horizon | before_earliest_end_whole_windows | 14 | SELENA_12, SELENA_13 | 139.566 | 3582.431 | 918.837 | 8 of 8 |
| pipeline_2020_horizon | after_unified_scheduler | 9 | none | 14.902 | 3228.285 | 860.833 | 8 of 8 |
| integrated_2030_shifted_96h | before_adaptive_storage_rolling | 6 | SELENA_11, SELENA_12 | 9.917 | 1592.344 | 795.482 | 8 of 8 |
| integrated_2030_shifted_96h | after_unified_scheduler | 8 | none | 11.38 | 1491.834 | 747.836 | 8 of 8 |
