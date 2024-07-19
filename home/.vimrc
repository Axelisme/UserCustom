set t_Co=256
colo torte
set laststatus=1
set showcmd
set expandtab
syntax enable
let &t_SI = "\e[6 q"
let &t_EI = "\e[2 q"
" 行号
set nu
" 取消自動換行
set nowrap
" 相对行号
set relativenumber
augroup relative_number
  autocmd!
  autocmd BufLeave,FocusLost,InsertEnter   * set norelativenumber
  autocmd BufEnter,FocusGained,InsertLeave * set relativenumber
  autocmd BufEnter * :syntax sync fromstart
augroup END
" 行号背景
hi LineNr ctermbg=235 
" set autowrite
set updatetime=100
" 鼠标支持
set mouse=a
" 自動對齊
set ai
" 向右或向左一個縮排的寬度
set shiftwidth=4
" 啟用依照檔案類型，決定自動縮排樣式的功能
filetype indent on
" 高亮
hi Cursor cterm=reverse ctermbg=22
set cursorline
hi CursorLine   cterm=NONE ctermbg=235 ctermfg=none 
hi LineNr term=underline ctermfg=249 ctermbg=235 guifg=#b0b0b0
hi CursorLineNr term=bold ctermfg=214 gui=bold guifg=Yellow
hi SyntasticErrors cterm=none ctermbg=darkred
hi QuickFixLine cterm=none ctermfg=8 ctermbg=52
hi Normal ctermfg=254 ctermbg=234 guifg=#d0d0d0 guibg=#202020
hi MatchParen ctermfg=15 ctermbg=2 gui=underline guifg=#61AFEF
" 分隔条
hi VertSplit ctermfg=8 ctermbg=234 guifg=#e0e0e0 guibg=#000000
" 注释
hi Comment ctermfg=66
