{
  description = "My Home Manager configuration";

  inputs = {
    nixpkgs.url = "nixpkgs/nixos-unstable";
  };

  outputs = { nixpkgs, ... }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs { inherit system; };
    in {
      devShells.${system}.default = pkgs.mkShell {
        buildInputs = with pkgs; [
          hello  # for test
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
      };
    };
}
