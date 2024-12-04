return {
  {
    "zbirenbaum/copilot.lua",
    optional = true,
    init = function()
      -- autocmd for disable copilot when leaving insert mode
      vim.api.nvim_create_autocmd("InsertLeave", {
        group = vim.api.nvim_create_augroup("copilot-insert-leave", { clear = true }),
        desc = "disable copilot when leaving insert mode",
        callback = function()
          require("copilot.suggestion").dismiss()
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
