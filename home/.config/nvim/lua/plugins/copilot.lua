return {
  {
    "zbirenbaum/copilot.lua",
    optional = true,
    init = function()
      -- hidden copilot suggestion when in blink menu
      vim.api.nvim_create_autocmd("User", {
        pattern = "BlinkCmpMenuOpen",
        callback = function()
          require("copilot.suggestion").dismiss()
          vim.b.copilot_suggestion_hidden = true
        end,
      })
      vim.api.nvim_create_autocmd("User", {
        pattern = "BlinkCmpMenuClose",
        callback = function()
          vim.b.copilot_suggestion_hidden = false
        end,
      })

      -- autocmd for disable copilot when leaving insert mode
      vim.api.nvim_create_autocmd("InsertLeave", {
        group = vim.api.nvim_create_augroup("copilot-insert-leave", { clear = true }),
        desc = "disable copilot when leaving insert mode",
        callback = function()
          local sug = require("copilot.suggestion")
          if sug ~= nil then
            sug.dismiss()
          end
        end,
      })
    end,
    opts = {
      suggestion = {
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
}
