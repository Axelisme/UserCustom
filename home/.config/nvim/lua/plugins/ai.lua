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
}
