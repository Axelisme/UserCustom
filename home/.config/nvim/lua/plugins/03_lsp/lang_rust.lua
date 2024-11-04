return {
  {
    "neovim/nvim-lspconfig",
    opts = {
      setup = {
        -- fix conflict with rustaceanvim
        rust_analyzer = function()
          return true
        end,
      },
    },
  },
}
