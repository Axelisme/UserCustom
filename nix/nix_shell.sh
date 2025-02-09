pkgs=(
  zsh
  curl
  ncurses
  fd
  fzf
  lsd
  oh-my-posh
  yazi
  lazygit
  micromamba
  neovim
)

# alias nix_shell="NP_RUNTIME=proot nix-portable nix shell nixpkgs#{$(IFS=,echo "${pkgs[*]}")} -c zsh}"
# above line is not working, so I have to use the following line
# convert pkgs to string
pkgs_str=$(IFS=,; echo "${pkgs[*]}")
alias nix_shell="NP_RUNTIME=proot nix-portable nix shell nixpkgs#{$pkgs_str} -c zsh"
