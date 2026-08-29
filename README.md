# PJSK to TDA Auto Converter

This is a Blender add-on I made for my own use to fix several issues in motions extracted from PJSK. It converts an existing Action for a common TDA armature by comparing the source and target rest poses. Support for common Japanese and English bone names was added later so the add-on is not tied to one specific model.

Tested with Blender 4.2.22 LTS.

## Download

[Download the latest `PJSK_TDA_AutoConverter.zip`](https://github.com/hayasaka4042/pjsk-tda-auto-converter/releases/latest/download/PJSK_TDA_AutoConverter.zip)

## Installation and use

1. In Blender, open `Edit > Preferences > Add-ons > Install from Disk` and select `PJSK_TDA_AutoConverter.zip`.
2. Import the TDA model and motion as usual.
3. If the scene contains more than one compatible armature, select the one you want to use.
4. Open the `PJSK→TDA` tab in the 3D View sidebar and click `Convert Selected Action`.

If no Action is selected in the panel, the add-on uses the Action currently assigned to the target armature. The converted Action is assigned automatically when the conversion finishes.

## What it does

- Recognizes common Japanese and English TDA bone names, including MMD Tools `name_j` and `name_e` metadata.
- Uses the actual rest matrices of the target model instead of requiring one exact TDA skeleton.
- Handles common TDA helper chains such as Shoulder P/C, Waist Cancel, and Leg D bones.
- Converts `Dummy_L/R` when present and skips them when the model does not have them.
- Turns off the leg and toe IK constraints used by the target rig and checks that they stay off during the converted Action.
- Writes quaternion location/rotation curves without scale curves and leaves the source Action unchanged.
- Creates a validation report in Blender's Text Editor.

The conversion creates:

- `<output name>` — the converted Action.
- `<output name>_LowerBody_WORLD_BAKE` — a LowerBody world/armature-space reference Action.
- `<output name>_validation.txt` — bone mapping, frame range, IK state, and matrix error information.

## Limitations

This is an Action converter, not a PMX/VMD importer and not a foot-contact or foot-sliding fixer. It is intended for common TDA-style rigs, not every custom MMD armature. Missing core bones, ambiguous bone names, or constraints that prevent the target pose from matching will stop the conversion instead of being guessed around.

## Credits / test asset

The following model was used locally to check armature-name compatibility:

- `Tda式初音ミク Mトレース用モデル` — Tda / 金子卵黄 / suwaviola

Only its armature structure was used for local compatibility checks. No model, texture, motion, music, or other third-party asset is included in this repository or in the add-on ZIP. The model name, character, and assets remain subject to their original authors' terms of use.

## Disclaimer and modification

This is an unofficial personal project. It is not affiliated with or endorsed by SEGA, Colorful Palette, Crypton Future Media, Tda, or the model authors listed above.

Back up the `.blend` file and the original Action before using the add-on. If the code has a problem or does not fit your model, feel free to modify the add-on code for your own setup. This permission applies only to the add-on code and does not grant any rights to the models, motions, textures, music, or other third-party assets mentioned here.

Detailed test results are kept in [PJSK_TDA_AutoConverter_validation.md](PJSK_TDA_AutoConverter_validation.md).

---

# PJSK → TDA 自動轉換器

這只是一個基於個人需求，為了修復從 PJSK 提取的動作中某些問題而製作的 Blender 插件。它會比較來源與目標骨架的 Rest Pose，把現有 Action 轉到常見的 TDA 骨架上。後來補上常見日文、英文骨名的辨識，因此不再只綁定單一模型。

目前以 Blender 4.2.22 LTS 測試。

## 下載

[下載最新版 `PJSK_TDA_AutoConverter.zip`](https://github.com/hayasaka4042/pjsk-tda-auto-converter/releases/latest/download/PJSK_TDA_AutoConverter.zip)

## 安裝與使用

1. 在 Blender 打開 `編輯 > 偏好設定 > 附加元件 > 從磁碟安裝`，選擇 `PJSK_TDA_AutoConverter.zip`。
2. 照平常的方式匯入 TDA 模型與動作。
3. 場景裡如果有多個相容骨架，先選取要使用的骨架。
4. 打開 3D View 右側欄的 `PJSK→TDA` 分頁，按下 `轉換所選 Action`。

面板沒有指定 Action 時，插件會使用目標骨架目前套用的 Action。轉換結束後會自動切換到新 Action。

## 會處理的內容

- 辨識常見 TDA 日文、英文骨名，以及 MMD Tools 的 `name_j`／`name_e` 資料。
- 使用目標模型本身的 Rest Matrix，不要求骨架尺寸與單一模板完全相同。
- 處理常見的肩 P／C、腰取消與 Leg D 中介骨鏈。
- 模型有 `Dummy_L/R` 就轉換，沒有則略過。
- 關閉目標骨架的腿部與腳尖 IK，並確認轉換後的 Action 播放期間沒有重新啟用。
- 輸出 Quaternion 的位置與旋轉曲線，不建立 Scale 曲線，也不修改來源 Action。
- 在 Blender Text Editor 留下一份轉換驗證紀錄。

每次轉換會建立：

- `<輸出名稱>`：轉換後的 Action。
- `<輸出名稱>_LowerBody_WORLD_BAKE`：LowerBody 的世界／骨架空間參考 Action。
- `<輸出名稱>_validation.txt`：骨名配對、幀範圍、IK 狀態與矩陣誤差。

## 限制

這是 Action 轉換器，不負責匯入 PMX／VMD，也不會修正腳底接觸或滑步。它是給常見 TDA 類型骨架使用，不保證每一支自製 MMD 骨架都能直接轉換。核心骨缺失、骨名無法唯一判斷，或既有 Constraint 讓目標姿勢無法重現時，插件會停止，不會自行猜骨頭。

## 借物表／測試素材

以下模型只用於本機骨架名稱相容性檢查：

- `Tda式初音ミク Mトレース用モデル` — Tda／金子卵黄／suwaviola

測試只讀取骨架結構。這個儲存庫與插件 ZIP 都沒有包含模型、貼圖、動作、音樂或其他第三方素材。模型名稱、角色與素材的權利及使用條款仍屬原作者所有。

## 免責聲明與修改

這是基於個人使用需求製作的非官方插件，與 SEGA、Colorful Palette、Crypton Future Media、Tda 及上述模型作者沒有隸屬或官方合作關係。

使用前請先備份 `.blend` 與原始 Action。插件如果有問題，或不符合你的模型，可以自行修改插件程式碼。這項允許只針對插件程式碼，不代表取得本文提到的模型、動作、貼圖、音樂或其他第三方素材權利。

較完整的測試數據放在 [PJSK_TDA_AutoConverter_validation.md](PJSK_TDA_AutoConverter_validation.md)。
