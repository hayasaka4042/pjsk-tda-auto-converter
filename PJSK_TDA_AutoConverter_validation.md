# PJSK → TDA Auto Converter 驗證

## 1.2.1 不同體型與自製骨架相容性

- Blender：4.2.22 LTS；五個模型皆以實際插件程式完整轉換 1–4036。
- `PPPP TETO`：PASS，最大 Basis 重播誤差 `4.76837158203125e-07`；來源 Action digest 前後一致，Scale／IK curves 為 0。
- `PPPP MIKU`：PASS，最大 Basis 重播誤差 `4.76837158203125e-07`；來源 Action digest 前後一致，Scale／IK curves 為 0。
- `Tda式初音ミク Mトレース用モデル`：PASS，62 個輸出骨全部走標準橋接，最大 Basis 重播誤差 `4.76837158203125e-07`。
- `Midlander.pmx`：PASS；缺少選配 `Eyes`，自製階層不相容的 `Leg/LegTipEX/Neck` 保守保留輸入通道。
- `KAITOwCOAT+phy-RexZ-A.pmx`：PASS；缺少選配 `Eyes`，肩臂等自製中介骨鏈保守保留輸入通道。
- Midlander、KAITO 與 PPPP Teto 的實際 Mesh 於 3480–3580 以固定 FRONT／RIGHT、Z=0 地面基準檢查：未出現 v1.2.0 的爆體、手臂下墜、腿部拉伸或新增明顯抖動。
- 骨名配對改為「實際骨名優先、MMD metadata 次之」，避免 KAITO 的錯誤 metadata 蓋過正確骨名。
- v1.2.0 的失敗根因：直接要求不同體型／骨軸／父鏈的模型重現同一份完整世界姿勢，會製造過大的局部位移；同一套輸出矩陣驗證也把安全輸出誤判為失敗。1.2.1 改為已驗證 TDA 橋接、目標 Rest 骨軸換算、階層差異保守保留輸入通道，並驗證實際輸出的 Basis 可逐幀重播。

## 1.2.0 常見 TDA 相容性

- Blender：4.2.22 LTS。
- 英文標準骨名短範圍：PASS，434 F-Curves，最大矩陣誤差 `3.78489494e-06`。
- 全套日文骨名短範圍：PASS，62／62 語意骨配對，8 條日文 Action F-Curve 路徑自動重映射，最大誤差 `3.78489494e-06`。
- 任意 Blender 骨名、僅保留 MMD 日文名稱欄位：PASS，62／62 配對，最大誤差 `3.78489494e-06`。
- 不同 Rest Matrix 葉骨測試：PASS，最大誤差 `3.78489494e-06`。
- 缺少 `Dummy_L/R`：PASS，安全略過兩個非核心葉端骨，輸出 60 bones／420 F-Curves。
- 缺少核心 `Head`：正確 FAIL。
- 兩個骨同時宣告為 `Head`：正確以「骨名有歧義」FAIL，未猜測。
- 強制製造輸出矩陣失敗：正確恢復原 Action、6 個腿部 IK influence 與原 Rotation Mode，沒有留下半成品 Action。
- 原始 PMX 骨名辨識：
  - `Tda式初音ミク Mトレース用モデル`：62／62，6 個腿部 IK Constraint 找到。
  - `PPPP MIKU by ShyuuXi`：60／60，僅缺選配 `Dummy_L/R`，6 個腿部 IK Constraint 找到。
  - `PPPP TETO by ShyuuXi`：60／60，僅缺選配 `Dummy_L/R`，6 個腿部 IK Constraint 找到。
- Miku 完整 1–4036 回歸：PASS，434 F-Curves、1,751,624 keys，最大輸出矩陣誤差 `8.59797001e-06`；來源 Action digest 前後一致。

原始 PMX 抽查只驗證插件的骨名辨識；本機現有舊版 MMD Tools 在 Blender 4.2 匯入末段仍會碰到已移除的 `EditBone.layers` API。插件的完整動作驗證使用既有可正常工作的 TDA Blender 骨架與同一套全曲 Action。

## 1.1.0 新手流程與 IK 防呆

- Blender：4.2.22 LTS。
- Miku 完整範圍：1–4036。
- 測試起始狀態：左右 Knee／Ankle IK 與 Knee IK Limit influence 均設為 `1`。
- 輸出後狀態：6 個腿部相關 Constraint 全部為 `0`，完整驗證期間沒有重新啟用。
- 輸出：434 F-Curves、1,751,624 keys。
- 最大輸出矩陣誤差：`8.59797001e-06`。
- Miku／Airi／Shizuku 5 幀快速回歸：全部 PASS，最大誤差分別為 `4.41074371e-06`、`4.67896461e-06`、`4.00841236e-06`。
- 故意加入不相容 Constraint：正確停止、恢復原 Action 與原 IK influence，沒有留下失敗輸出 Action。
- 選取骨架自動辨識：PASS。

## 1.0.0 原始完整驗證

- 結果：**PASS**
- Blender：4.2.22 LTS
- 測試來源：`BLD/Patchwork Staccato1.blend`
- 測試 Action：`Miku_bone`
- 測試範圍：1–4036（4036 幀）
- 輸出：62 bones、434 FCurves、1,751,624 keys
- LowerBody world bake：7 FCurves、28,252 keys
- 來源 Action digest：建立前／完成後一致
- TDA rest matrix 最大差：0
- LowerBody bake 最大矩陣差：`5.364418029785156e-07`
- 輸出 evaluated pose 最大矩陣差：`8.612871170043945e-06`
- 輸出最大 translation 差：`3.385450689703712e-06`
- 最大 scale 偏差：`9.5367431640625e-07`
- 輸出 scale curves：0
- 輸出 IK curves：0
- 保存重開：PASS
- 與先前使用者確認預覽正常的全曲 PASS Action 比較：最大 FCurve 值差 `3.57627868652e-07`
- 單次全曲轉換與內建全幀驗證耗時：83.844 秒（本機測試）

工具只實作已驗證的 PJSK 相容來源骨架、LowerBody world bake，以及靜置姿勢相對矩陣轉移；不包含 Center 修正或 Foot FK。
