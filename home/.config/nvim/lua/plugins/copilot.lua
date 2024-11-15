In_ssh = os.getenv("SSH_TTY") ~= nil

return {
  {
    "zbirenbaum/copilot.lua",
    enabled = not In_ssh,
    opts = function()
      -- autocmd for disable copilot when leaving insert mode
      vim.api.nvim_create_autocmd("InsertLeave", {
        group = vim.api.nvim_create_augroup("copilot-insert-leave", { clear = true }),
        desc = "disable copilot when leaving insert mode",
        callback = function()
          require("copilot.suggestion").dismiss()
        end,
      })

      -- add ai accept function
      ---@diagnostic disable-next-line: duplicate-set-field
      LazyVim.cmp.actions.ai_accept = function()
        local has_words_before = function()
          local col = vim.fn.col(".")
          return vim.fn.getline("."):sub(1, col - 1):match("%S")
        end
        if has_words_before() and require("copilot.suggestion").is_visible() then
          LazyVim.create_undo()
          require("copilot.suggestion").accept()
          return true
        end
      end

      return {
        suggestion = {
          auto_trigger = true,
          keymap = {
            accept = "<C-Up>",
            accept_word = "<C-Right>",
            accept_line = "<C-Down>",
            dismiss = "<C-Left>",
          },
        },
        filetypes = { yaml = true },
      }
    end,
  },
}
