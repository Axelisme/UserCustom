return {
  {
    "neovim/nvim-lspconfig",
    optional = true,
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
