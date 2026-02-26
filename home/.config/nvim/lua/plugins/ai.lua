return {
  {
    "zbirenbaum/copilot.lua",
    optional = true,
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
  {
    "marcinjahn/gemini-cli.nvim",
    cmd = "Gemini",
    keys = {
      { "<c-g>", "<cmd>Gemini toggle<cr>", desc = "Toggle Gemini CLI", mode = { "n", "v", "t" } },
      { "<leader>aa", "<cmd>Gemini ask<cr>", desc = "Ask Gemini", mode = { "n", "v" } },
      { "<leader>af", "<cmd>Gemini add_file<cr>", desc = "Add File" },
    },
    opts = {
      win = {
        position = "right",
        width = 0.5,
      },
      interactive = true,
    },
  },
}
