# PJSK → TDA 自動轉換器

這是 Blender 4.2.22 的動畫轉換插件，用來把 PJSK／MMD Action 轉換到目前已驗證的 TDA 初音骨架。

## 最快使用方式

1. 在 Blender 的 `編輯 → 偏好設定 → 附加元件 → 從磁碟安裝` 選擇 `PJSK_TDA_AutoConverter.zip`。
2. 匯入 TDA 模型與動作；場景只有一個相容骨架時不必手動指定，否則請選取目標骨架。
3. 在 3D View 右側的 `PJSK→TDA` 面板按下 `轉換所選 Action`。

沒有在面板指定 Action 時，插件會使用目標骨架目前正在播放的 Action。轉換完成後會自動切換到新 Action。

## 插件會自動處理

- 依來源／目標 Rest Pose 的實際矩陣關係轉換動作。
- 自動關閉左右腿與腳尖 IK，並在完整輸出範圍逐幀確認沒有重新啟用。
- 保留原輸入 Action，不覆蓋既有輸出。
- 保持 Quaternion 連續，不建立 Scale 曲線。
- 驗證輸出 Pose 矩陣，失敗時回復原 Action 與原 IK 狀態。
- 在 Blender Text Editor 建立中文可讀的驗證報告。

## 會產生的資料

- `<輸出名稱>`：轉換後可直接播放的新 Action。
- `<輸出名稱>_LowerBody_WORLD_BAKE`：進階檢查用的 LowerBody 世界空間記錄。
- `<輸出名稱>_validation.txt`：轉換範圍、誤差、IK 狀態與來源保護結果。

## 適用範圍

- Blender 4.2.22 LTS。
- 目前插件內建模板所對應的 TDA 初音骨架。
- PJSK 相容的骨架 Action。

這個插件不負責匯入 PMX／VMD，也不是腳底接觸或腳滑修正器。骨名、父子關係或 Rest Pose 不相容時會停止，不會猜測轉換。

## 常見訊息

- `場景中有多個 TDA 骨架`：先選取要轉換的骨架再按一次。
- `請先選擇輸入 Action`：先把動作套到骨架，或在面板的「輸入 Action」選擇動作。
- `目標不是已驗證的 TDA 骨架`：目前模型和內建模板不相容。
- `腿部 IK 在 frame ... 被重新啟用`：Action、Driver 或其他設定正在控制 IK；插件已停止並恢復原狀。
