return {
  {
    "neovim/nvim-lspconfig",
    opts = function(_, opts)
      local keys = require("lazyvim.plugins.lsp.keymaps").get()
      -- disable <c-k> for navigate in insert mode
      keys[#keys + 1] = { "<c-k>", false, mode = "i" }
      -- disable <Tab> for indent in insert mode
      keys[#keys + 1] = { "<Tab>", false, mode = "i" }

      opts.inlay_hints = { enabled = false }
    end,
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
