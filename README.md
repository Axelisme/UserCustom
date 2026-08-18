# UserCustom Shell 設定

此專案包含一系列的 Shell 腳本，用於在 Linux 系統上安裝必要的軟體包並進行shell環境設定。以下是設定過程的步驟指南。

## 步驟 1: 安裝依賴

執行install_scripts裡的腳本，或請自行安裝相關軟體。  

### 步驟 1.1: 安裝zsh以及stew等基礎依賴

```bash
./install_scripts/install_zsh.sh
./install_scripts/install_stew.sh
./install_scripts/install_mamba.sh #(Optional)
```

### 步驟 1.2: 使用stew安裝其餘依賴(可自動追蹤最新版本)
```bash
stew install install_scripts/Stewfile
```

## 步驟 2: 設定 Shell 環境

安裝完必要的軟體包後，接下來您應該執行 `setup_shell` 腳本來設定您的 Shell 環境。這將包括配置 `.bashrc`、`.zshrc`  
以及執行`setup_config.sh`來設定其他配置文件。  
附帶配置文件的軟體包含：`vim`、`alacritty`、`nnn`、`neovim`、`ohmyposh`、`tmux` 等。

```bash
# setup .bashrc, .zshrc, and others
./setup_scripts/setup_shell.sh
./setup_scripts/setup_config.sh
```

## Agent skills 與 profiles

`home/.codex/skills/` 承載全部 personal agent skill，`home/.claude/skills/` 與
`home/.pi/agent/skills/` 是指向它的相對 symlink。上游來的 skill 本身也是 symlink，指進
`vendor/matt-skills/`——那是 `mattpocock/skills` 的 git subtree，同步方式見
`home/.codex/skills/UPSTREAM.md`；只有本地自有的 skill 與尚未納入 subtree 的 `grove` 是實體目錄。
`home/.claude/agents/*.md` 與 `home/.codex/agents/*.toml` 是 agent profile
（同一角色雙格式，修改請同 commit 動兩檔）。`setup_config.sh` 會把指定的設定項目以 symbolic
link 安裝到 `$HOME`；既有且不是正確 link 的項目會先改名為同路徑的 `.bak`（已有備份時使用
numbered backup）。

**注意**：symbolic link 會直接反映 `home/` 下的更新——包含穿過 `vendor/` 的那一段，所以同步
上游之後不需要重跑安裝。重跑 `./setup_scripts/setup_config.sh` 只會略過已正確連結的項目。產生的 `.bak` 可自行刪除。

## 步驟 3: 設定其他軟體(Optional)

```bash
./setup_scripts/setup_mamba.sh
./setup_scripts/setup_git.sh
./setup_scripts/setup_yazi.sh
./setup_scripts/setup_rime-frost.sh
```
