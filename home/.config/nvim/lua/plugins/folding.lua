return {
  -- add folding range to capabilities
  {
    "neovim/nvim-lspconfig",
    optional = true,
    opts = {
      capabilities = {
        textDocument = {
          foldingRange = {
            dynamicRegistration = false,
            lineFoldingOnly = true,
          },
        },
      },
    },
  },

  -- add nvim-ufo
  {
    "kevinhwang91/nvim-ufo",
    dependencies = "kevinhwang91/promise-async",
    event = "BufReadPost",
    keys = {
      { "zR", "<cmd>lua require('ufo').openAllFolds()<CR>" },
      { "zM", "<cmd>lua require('ufo').closeAllFolds()<CR>" },
    },
    opts = {
      open_fold_hl_timeout = 150,
      close_fold_kinds_for_ft = {
        default = { "comment" },
        json = { "array" },
        c = { "comment", "region" },
      },
    },
  },
}
