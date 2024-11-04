return {
  {
    "neovim/nvim-lspconfig",
    opts = function(_, opts)
      local keys = require("lazyvim.plugins.lsp.keymaps").get()
      -- disable <c-k> for navigate in insert mode
      keys[#keys + 1] = { "<c-k>", false, mode = "i" }
      keys[#keys + 1] = { "<c-i>", "<cmd>lua vim.lsp.buf.signature_help()<cr>", mode = "i" }
      -- disable <Tab> for indent in insert mode
      keys[#keys + 1] = { "<Tab>", false, mode = "i" }

      opts.inlay_hints = { enabled = false }
    end,
  },
}
