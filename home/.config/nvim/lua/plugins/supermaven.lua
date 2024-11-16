In_ssh = os.getenv("SSH_TTY") ~= nil

return {
  {
    "supermaven-inc/supermaven-nvim",
    optional = true,
    enabled = not In_ssh,
    opts = function()
      -- add ai accept function
      ---@diagnostic disable-next-line: duplicate-set-field
      LazyVim.cmp.actions.ai_accept = function()
        local has_words_before = function()
          local col = vim.fn.col(".")
          return vim.fn.getline("."):sub(1, col - 1):match("%S")
        end
        local suggestion = require("supermaven-nvim.completion_preview")
        if has_words_before() and suggestion.has_suggestion() then
          LazyVim.create_undo()
          vim.schedule(function()
            suggestion.on_accept_suggestion()
          end)
          return true
        end
      end

      return {
        keymaps = {
          accept_suggestion = "<C-Up>",
          accept_word = "<C-Right>",
          clear_suggestion = "<C-Left>",
        },
        color = {
          suggestion_color = "#6b6b6b",
          cterm = 244,
        },
      }
    end,
  },
}
