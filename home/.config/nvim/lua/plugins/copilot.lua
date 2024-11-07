local in_ssh = os.getenv("SSH_TTY") ~= nil

return {
  {
    "zbirenbaum/copilot.lua",
    enabled = not in_ssh,
    -- enabled = false,
    event = "InsertEnter",
    cmd = "Copilot",
    build = ":Copilot auth",
    dependencies = {
      {
        "AndreM222/copilot-lualine",
        lazy = true,
        config = function()
          local lualine = require("lualine")
          local cfg = lualine.get_config()
          table.insert(cfg.sections.lualine_x, 2, { "copilot", symbols = { show_colors = true } })
          lualine.setup(cfg)
        end,
      },
    },
    opts = function()
      -- autocmd for disable copilot when leaving insert mode
      vim.api.nvim_create_autocmd("InsertLeave", {
        group = vim.api.nvim_create_augroup("copilot-insert-leave", { clear = true }),
        desc = "disable copilot when leaving insert mode",
        callback = function()
          require("copilot.suggestion").dismiss()
        end,
      })

      return {
        panel = { enabled = false },
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
        filetypes = { yaml = true, markdown = true },
      }
    end,
  },
  {
    "saghen/blink.cmp",
    optional = true,
    opts = {
      keymap = {
        ["<Tab>"] = {
          "snippet_forward",
          function()
            if in_ssh then
              return false
            end
            local has_words_before = function()
              local col = vim.fn.col(".")
              return vim.fn.getline("."):sub(1, col - 1):match("%S")
            end
            if not has_words_before() or not require("copilot.suggestion").is_visible() then
              return false
            end
            LazyVim.create_undo()
            require("copilot.suggestion").accept()
            return true
          end,
          "fallback",
        },
      },
    },
  },
}
