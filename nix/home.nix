{ pkgs, ... }:

{
  home = {
    username = "axel";
    homeDirectory = "/home/axel";
    stateVersion = "23.11";

    packages = with pkgs; [
      home-manager
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
    ];

    file = {
      # ".bashrc".source = ../home/.bashrc;
      # ".zshrc".source = ../home/.zshrc;
      # ".vimrc".source = ../home/.vimrc;
    };
  };

  xdg.configFile = {
    # 部署oh-my-posh主题
    # "ohmyposh".source = ../home/.config/ohmyposh;
  };
}
