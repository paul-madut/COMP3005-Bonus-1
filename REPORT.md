# Performance report

## Setup

- Machine: Apple M2, macOS 26.5.2
- Language: Python 3.12.1 (CPython)
- Engine: nested loop join, no indexes, no optimisation
- Timing method:
- Data generator command:

## Join experiment

Query: `R join[R.b=S.b] S`

| n | m | comparisons | wall time (s) | output tuples |
|---|---|---|---|---|
| 1000 | 1000 | | | |
| 2000 | 2000 | | | |
| 4000 | 4000 | | | |
| 8000 | 8000 | | | |
| 16000 | 16000 | | | |
| 32000 | 32000 | | | |
| 64000 | 64000 | | | |

## Questions

### Q1. Relationship between n, m and the comparison count

### Q2. Log-log slope of time against n

### Q3. Select and project compared with the join

### Q4. Predicted time for one million tuples per side

### Q5. Effect of the match rate

### Q6. Making the million-tuple join feasible
