# 公館路口號誌最佳化

[中文提案 PDF](report/Gongguan_BO_Proposal_ZH.pdf) · [英文提案 PDF](report/Gongguan_BO_Proposal_EN.pdf) · [原版中文提案 PDF](report/Gongguan_BO_Proposal.pdf)

## 問題與目標

我搭公車經過公館時，有時得等好幾輪紅燈才能左轉進基隆路。步行過街時，我覺得等待仍在可接受的範圍。這個 prototype 探討尖峰號誌能否縮短公車延誤，同時兼顧行人與一般車流。模擬使用整體公車排隊延誤，實際左轉動線仍待建模。

我們用 BoTorch 的 qLogNEHVI 搜尋兩個參數：號誌週期（100–160 秒）和主幹道可分配綠燈比例（45–65%）。三個最佳化目標是公車平均延誤、行人等待 P95 和一般車平均延誤。平均情境 MOBO 對三種情境取平均，最壞情境 MOBO 對每項指標各取情境最大值。兩者都與隨機搜尋及固定合成時制比較。

## 實驗結果

![三目標搜尋進度與保留情境的方案取捨](results/results.png)

左圖比較三種搜尋方法的訓練穩健 hypervolume，線為四次重跑的中位數，陰影為最小至最大值。右圖以第 1 次搜尋的保留情境為例，橫軸與縱軸為公車延誤和行人等待，候選圓點的填色代表一般車延誤，空心圈為在訓練情境屬於三目標 Pareto front 的方案。

| 方法 | 公車平均延誤（秒） | 行人等待 P95（秒） | 一般車平均延誤（秒） |
| --- | ---: | ---: | ---: |
| 固定合成時制 | 133.7 | 79.1 | 38.5 |
| 平均情境 MOBO | 124.4 | 66.6 | 48.7 |
| 最壞情境 MOBO | 124.4 | 66.8 | 48.8 |
| 隨機搜尋 | 102.3 | 73.4 | 57.3 |

各指標先取最壞保留情境，再對四次搜尋取中位數。三欄都愈低愈好。

隨機搜尋的公車延誤最低，兩種 MOBO 的行人等待和一般車延誤都比隨機搜尋低。最壞情境 MOBO 的訓練 hypervolume 中位數比隨機搜尋高約 12%。固定合成時制的一般車延誤仍最低。兩種 MOBO 的保留情境結果相近。

## 重跑與示範

建議使用 Python 3.11。所有到達資料均由程式生成。

```sh
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python experiment.py
```

- 快速示範可跑 `python experiment.py --budget 8 --runs 1 --output /tmp/gongguan-demo`。
- 比較任意兩組時制可跑 `python simulator.py --cycle 130 --share 0.55` 與 `python simulator.py --cycle 105 --share 0.62`。
- 完整實驗每個搜尋方法跑四次，每次評估 20 組時制，三種搜尋方法共用前四組 Sobol 候選。平均情境 MOBO 以三個平均情境指標選代表方案，最壞情境 MOBO 與隨機搜尋都用各指標的最壞情境值選代表方案。選擇時各指標先除以 150 秒再等權加總。訓練穩健 hypervolume 以三個最壞情境指標計算，參考點為各 150 秒。

| 產出 | 用途 |
| --- | --- |
| [逐輪搜尋紀錄](results/trials.csv) | 查每組候選在各訓練情境的三項指標與當時的訓練穩健 hypervolume |
| [三目標 Pareto 方案](results/pareto.csv) | 依每次最壞情境 MOBO 的訓練結果列出未被支配的時制，並標記代表方案 |
| [保留情境評估](results/holdout.csv) | 查各方法選出方案後的測試結果 |

模擬包含一般尖峰、公車成團到達和橫向車流尖峰。訓練每情境使用四個亂數樣本，保留測試提高到達率並使用十二個新樣本。模型使用獨立佇列和合成需求。若要作為現地時制建議，需先校準實際交通量與現行相位，再檢查轉向衝突、相鄰路口回堵及行人安全。

## 參考資料

- [臺北市新建工程處：公館圓環改造](https://english.nco.gov.taipei/News_Content.aspx?n=C43859DE9907C884&s=B408C94159CBDBA6)
- [Google Research：Project Green Light](https://sites.research.google/gr/greenlight/)
- [Kinnunen 等人：Maximally Robust Satisficing Bayesian Optimization](https://proceedings.mlr.press/v337/kinnunen26a.html)
- [BoTorch：多目標 BO 教學](https://botorch.org/docs/v0.16.1/tutorials/multi_objective_bo)
