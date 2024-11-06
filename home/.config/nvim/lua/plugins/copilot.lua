local in_ssh = os.getenv("SSH_TTY") ~= nil

return {
  {
    "zbirenbaum/copilot.lua",
    enabled = not in_ssh,
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
      -- Super Tab
      vim.keymap.set("i", "<Tab>", function()
        local cpl = require("copilot.suggestion")
        if cpl.is_visible() then
          cpl.accept()
        else
          local key = vim.api.nvim_replace_termcodes("<Tab>", true, false, true)
          vim.api.nvim_feedkeys(key, "n", false)
        end
      end)
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
}
