# CSV → DB Migration — Reconciliation Report

- Source: `/Users/berco/Analysis/futpage/cernyfoot/static`
- Run at: 2026-07-08T09:34:09

## Counts

- **players_registered**: 22
- **players_guest**: 12
- **admins**: 4
- **seasons**: 2
- **holidays**: 34
- **matches_total**: 71
- **matches_played**: 54
- **matches_cancelled**: 16
- **matches_scheduled**: 1
- **signups**: 510
- **payments**: 22

## Score-drift resolutions (rule D2: first data row wins)

- `2025-01-23.csv`: scores seen ['8:11', '8:10'] → canonical **8:11**
- `2025-03-06.csv`: scores seen ['6:3', '0:0'] → canonical **6:3**

## Guest players created (excluded from standings)

- denis K
- rudo
- MatoP
- Marek
- Jarek
- Michal (Rado)
- Riso2
- Daniel H
- Michal H
- ondrej+1
- Ondrej+1
- Miro

## Skipped files

- `19:00.csv`

## Warnings

- past match 2026-02-19 has no players and no result — imported as scheduled (original stats counted it as played)
- rado missing from subscriptions.csv — defaulted to Nevyplatené
