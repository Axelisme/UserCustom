local cmp = require("cmp")

return {
  -- copilot
  {
    "zbirenbaum/copilot.lua",
    -- enabled = false,
    event = "InsertEnter",
    cmd = "Copilot",
    build = ":Copilot auth",
    opts = {
      suggestion = {
        enabled = true,
        auto_trigger = true,
        keymap = {
          accept = "<C-Up>",
          accept_word = "<C-Right>",
          accept_line = "<C-Down>",
          dismiss = "<C-Left>",
        },
      },
    },
  },

  -- copilot icon
  {
    "nvim-lualine/lualine.nvim",
    optional = true,
    event = "VeryLazy",
    opts = function(_, opts)
      local colors = {
        [""] = LazyVim.ui.fg("Special"),
        ["Normal"] = LazyVim.ui.fg("Special"),
        ["Warning"] = LazyVim.ui.fg("DiagnosticError"),
        ["InProgress"] = LazyVim.ui.fg("DiagnosticWarn"),
      }
      table.insert(opts.sections.lualine_x, 2, {
        function()
          local icon = LazyVim.config.icons.kinds.Copilot
          local status = require("copilot.api").status.data
          return icon .. (status.message or "")
        end,
        cond = function()
          if not package.loaded["copilot"] then
            return
          end
          local ok, clients = pcall(LazyVim.lsp.get_clients, { name = "copilot", bufnr = 0 })
          if not ok then
            return false
          end
          return ok and #clients > 0
        end,
        color = function()
          if not package.loaded["copilot"] then
            return
          end
          local status = require("copilot.api").status.data
          return colors[status.status] or colors[""]
        end,
      })
    end,
  },

  -- override source of nvim-cmp for above line menu
  {
    "hrsh7th/nvim-cmp",
    enabled = false,
    opts = {
      experimental = { ghost_text = false },
      mapping = {
        ["<CR>"] = cmp.mapping(function(fallback)
          cmp.abort()
          fallback()
        end, { "i", "s" }),
        ["<Down>"] = cmp.config.disable,
        ["<Up>"] = cmp.config.disable,
        ["<S-j>"] = cmp.mapping.select_next_item(),
        ["<S-Down>"] = cmp.mapping.select_next_item(),
        ["<S-k>"] = cmp.mapping.select_prev_item(),
        ["<S-Up>"] = cmp.mapping.select_prev_item(),
        ["<S-CR>"] = cmp.mapping.confirm({ select = true }),
      },
    },
  },
  {
    "llllvvuu/nvim-cmp",
    branch = "feat/above",
    enabled = true,
    opts = {
      view = {
        entries = { vertical_positioning = "above", follow_cursor = true },
      },
    },
  },
}
