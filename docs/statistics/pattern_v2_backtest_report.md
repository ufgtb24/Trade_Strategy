# Pattern Label v2 Backtest Report

Sample size: **9791** breakout events

## Executive Summary

**5/7 hypotheses passed.**

- **H1**: FAIL
- **H2**: PASS
- **H3**: FAIL
- **H4**: PASS
- **H5**: PASS
- **H6**: PASS
- **H7**: PASS

## 1. v2 Pattern Distribution

| pattern | count | pct |
| --- | --- | --- |
| power_surge | 101 | 1.0 |
| volume_breakout | 626 | 6.4 |
| strong_momentum | 171 | 1.7 |
| momentum | 698 | 7.1 |
| dormant_awakening | 630 | 6.4 |
| dip_recovery | 4791 | 48.9 |
| crowded_breakout | 2441 | 24.9 |
| basic | 333 | 3.4 |


Max pattern share: 48.9% (WARNING: >30%)

## 2. Old vs New Pattern Stats

### 2.1 Old Patterns (v1)

| pattern | count | mean | median | std | q25 | q75 |
| --- | --- | --- | --- | --- | --- | --- |
| volume_surge | 81 | 0.4271 | 0.2755 | 0.5004 | 0.1427 | 0.4596 |
| power_historical | 164 | 0.4338 | 0.2742 | 0.5056 | 0.1415 | 0.5718 |
| dense_test | 8 | 0.2103 | 0.2074 | 0.0720 | 0.2074 | 0.2380 |
| deep_rebound | 513 | 0.2786 | 0.1791 | 0.3251 | 0.1037 | 0.3508 |
| dormant_breakout | 88 | 0.2393 | 0.1734 | 0.2124 | 0.0897 | 0.3391 |
| momentum | 5714 | 0.2739 | 0.1721 | 0.3545 | 0.0953 | 0.3249 |
| historical | 943 | 0.2294 | 0.1478 | 0.2591 | 0.0744 | 0.3018 |
| basic | 255 | 0.2349 | 0.1371 | 0.3514 | 0.0763 | 0.2656 |
| grind_through | 445 | 0.2108 | 0.1340 | 0.2736 | 0.0713 | 0.2682 |
| trend_continuation | 1580 | 0.2048 | 0.1283 | 0.2406 | 0.0705 | 0.2452 |


### 2.2 New Patterns (v2)

| pattern | count | mean | median | std | q25 | q75 |
| --- | --- | --- | --- | --- | --- | --- |
| power_surge | 101 | 0.4702 | 0.3072 | 0.5369 | 0.1807 | 0.5574 |
| volume_breakout | 626 | 0.4423 | 0.2473 | 0.5966 | 0.1326 | 0.4738 |
| dormant_awakening | 630 | 0.3187 | 0.2159 | 0.3749 | 0.1148 | 0.3953 |
| strong_momentum | 171 | 0.3385 | 0.2069 | 0.4072 | 0.1119 | 0.4500 |
| momentum | 698 | 0.2505 | 0.1691 | 0.2669 | 0.0908 | 0.3274 |
| dip_recovery | 4791 | 0.2511 | 0.1612 | 0.3030 | 0.0916 | 0.3045 |
| basic | 333 | 0.2239 | 0.1358 | 0.3169 | 0.0740 | 0.2645 |
| crowded_breakout | 2441 | 0.2027 | 0.1283 | 0.2431 | 0.0688 | 0.2485 |


## 3. Hypothesis Test Details

### H1: Inter-pattern discrimination

- Kruskal-Wallis H = 367.4939 (threshold: 236)
- Kruskal-Wallis p = 0.0000 ***
- All adjacent pairs significant: No
- **Result: FAIL**

| pair | median_a | median_b | p_value | sig |
| --- | --- | --- | --- | --- |
| power_surge vs volume_breakout | 0.3072 | 0.2473 | 0.0462 | * |
| volume_breakout vs strong_momentum | 0.2473 | 0.2069 | 0.0561 |  |
| strong_momentum vs momentum | 0.2069 | 0.1691 | 0.0070 | ** |
| momentum vs dormant_awakening | 0.1691 | 0.2159 | 0.0000 | *** |
| dormant_awakening vs dip_recovery | 0.2159 | 0.1612 | 0.0000 | *** |
| dip_recovery vs crowded_breakout | 0.1612 | 0.1283 | 0.0000 | *** |
| crowded_breakout vs basic | 0.1283 | 0.1358 | 0.3741 |  |


### H2: power_surge is the best pattern

- power_surge median = 0.3072 (n=101)
- momentum median = 0.1691
- Mann-Whitney p = 0.0000 ***
- **Result: PASS**

### H3: crowded_breakout worse than basic

- crowded median = 0.1283 (n=2441)
- basic median = 0.1358 (n=333)
- Mann-Whitney p = 0.3741 
- **Result: FAIL**

### H4: Old momentum effectively split

- Old momentum: n=5714 (58.4%)
- New momentum: n=698 (7.1%)
- strong_momentum median = 0.2069
- momentum median = 0.1691
- Mann-Whitney p = 0.0070 **
- **Result: PASS**

Destination of old momentum samples:

| pattern_v2 | count | pct |
| --- | --- | --- |
| dip_recovery | 4427 | 77.5 |
| dormant_awakening | 527 | 9.2 |
| volume_breakout | 358 | 6.3 |
| momentum | 320 | 5.6 |
| strong_momentum | 65 | 1.1 |
| power_surge | 16 | 0.3 |
| basic | 1 | 0.0 |


### H5: Drought nonlinearity in dormant_awakening

- Drought level 1: median = 0.2508 (n=252)
- Drought level 2+: median = 0.1980 (n=378)
- **Result: PASS**

### H6: Volume+Streak samples not wrongly degraded

- Samples with Streak>=1 & Volume>=1: n=307
- In Tier 1/2: 307 (100%)
- Median = 0.2622
- **Result: PASS**

| pattern | count |
| --- | --- |
| volume_breakout | 226 |
| power_surge | 81 |


### H7: DayStr adds value to strong_momentum

- strong_momentum median = 0.2069 (n=171)
- momentum median = 0.1691 (n=698)
- Mann-Whitney p = 0.0070 **
- **Result: PASS**

## 4. Recommendations

Failed hypotheses: H1, H3. Review these before proceeding:

- **H1**: Consider adjusting thresholds or merging related patterns.
- **H3**: Consider adjusting thresholds or merging related patterns.

## Appendix: Full Pairwise Mann-Whitney

| pattern_a | pattern_b | u_stat | p_value | significance |
| --- | --- | --- | --- | --- |
| volume_breakout | crowded_breakout | 1046785.5000 | 0.0000 | *** |
| dormant_awakening | crowded_breakout | 992860.5000 | 0.0000 | *** |
| volume_breakout | dip_recovery | 1875920.5000 | 0.0000 | *** |
| dip_recovery | crowded_breakout | 6673664.5000 | 0.0000 | *** |
| volume_breakout | basic | 140061.0000 | 0.0000 | *** |
| power_surge | crowded_breakout | 184517.5000 | 0.0000 | *** |
| power_surge | basic | 24742.0000 | 0.0000 | *** |
| volume_breakout | momentum | 267909.0000 | 0.0000 | *** |
| dormant_awakening | basic | 132539.0000 | 0.0000 | *** |
| power_surge | dip_recovery | 335446.5000 | 0.0000 | *** |
| dormant_awakening | dip_recovery | 1752833.5000 | 0.0000 | *** |
| momentum | crowded_breakout | 990043.5000 | 0.0000 | *** |
| strong_momentum | crowded_breakout | 267535.5000 | 0.0000 | *** |
| power_surge | momentum | 48006.5000 | 0.0000 | *** |
| strong_momentum | basic | 35738.0000 | 0.0000 | *** |
| dormant_awakening | momentum | 249798.5000 | 0.0000 | *** |
| power_surge | dormant_awakening | 39271.5000 | 0.0002 | *** |
| strong_momentum | dip_recovery | 473242.5000 | 0.0005 | *** |
| momentum | basic | 131618.0000 | 0.0006 | *** |
| dip_recovery | basic | 885604.5000 | 0.0008 | *** |
| power_surge | strong_momentum | 10571.5000 | 0.0020 | ** |
| volume_breakout | dormant_awakening | 217016.5000 | 0.0020 | ** |
| strong_momentum | momentum | 67615.0000 | 0.0070 | ** |
| power_surge | volume_breakout | 35518.0000 | 0.0462 | * |
| volume_breakout | strong_momentum | 58620.0000 | 0.0561 |  |
| momentum | dip_recovery | 1712882.5000 | 0.2966 |  |
| basic | crowded_breakout | 418612.0000 | 0.3741 |  |
| dormant_awakening | strong_momentum | 53639.0000 | 0.9330 |  |

