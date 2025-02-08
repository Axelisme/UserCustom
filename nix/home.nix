{ lib, pkgs, ... }:
{
  home = {
    packages = with pkgs; [
      home-manager
      # neovim
      curl
      yazi
      lazygit
      micromamba
      oh-my-posh
    ];

    # This needs to actually be set to your username
    username = "axel";
    homeDirectory = "/home/axel";

    # You do not need to change this if you're reading this in the future.
    # Don't ever change this after the first build.  Don't ask questions.
    stateVersion = "23.11";
  };
}
