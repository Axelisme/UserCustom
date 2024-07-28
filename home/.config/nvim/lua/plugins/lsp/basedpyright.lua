return {
  "neovim/nvim-lspconfig",
  opts = {
    servers = {
      basedpyright = {
        settings = {
          pyright = {
            -- Using Ruff's import organizer
            disableOrganizeImports = true,
          },
          basedpyright = {
            analysis = {
              -- Basic type checking
              typeCheckingMode = "basic",
            },
          },
        },
      },
    },
  },
}
