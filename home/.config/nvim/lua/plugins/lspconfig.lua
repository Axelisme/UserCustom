return {
  {
    "neovim/nvim-lspconfig",
    opts = {
      servers = {
        ["*"] = {
          keys = {
            { "<c-k>", false, mode = "i" },
            { "<Tab>", false, mode = "i" },
          },
        },
      },
      inlay_hints = { enabled = false },
    },
  },
  {
    "folke/noice.nvim",
    optional = true,
    opts = {
      lsp = {
        signature = {
          opts = { size = { max_height = math.floor(vim.api.nvim_win_get_height(0) / 2) } },
        },
      },
    },
  },
}
