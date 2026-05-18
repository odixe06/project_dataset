# Dataset Stats Report

Total samples: 415670

## Counts By Label
{'0': 402203, '1': 13467}

## Counts By Source And Label
{'auto_capture_hf|1': 533, 'cesnet_miner22|1': 10000, 'cj_sniffer|1': 218, 'hikari2021|0': 229089, 'iot23_mcfp|0': 173114, 'mineshark_artifact|1': 2716}

## TLS Coverage
{'0|0': 173114, '0|1': 229089, '1|0': 13383, '1|1': 84}

## Sequence Coverage
{'0|0.0': 285885, '0|nan': 116318, '1|0.0': 2716, '1|1.0': 10725, '1|nan': 26}

## Warnings
- none

## Errors
- none

## Training Notes
- Do not use provenance columns as default model inputs.
- Prefer source/file group splits for downstream generalization checks.
