###################################################
# myset.sh
source $USER_CUSTOM/rc/myset.sh

###################################################
# zsh
# 移除重复的命令历史
setopt HIST_IGNORE_ALL_DUPS
# 设置可以使用通配符
setopt nonomatch
# 有些theme需要設定這才能正常顯示
setopt promptsubst

# 加载zinit
source $ZINIT_PATH

# 加载主题
zinit light romkatv/powerlevel10k

# 插件
## 语法高亮
zinit light zdharma-continuum/fast-syntax-highlighting
## 补全
zinit light zsh-users/zsh-completions
## 根据子串搜索历史命令
zinit light zsh-users/zsh-autosuggestions
## 萬用解壓縮指令
zinit snippet OMZP::extract
## 双击esc快速在命令前添加或删除sudo
zinit snippet OMZP::sudo
## git插件
zinit snippet OMZP::git
## 加载 OMZ 框架及
zinit snippet OMZL::completion.zsh
zinit snippet OMZL::history.zsh
zinit snippet OMZL::key-bindings.zsh
