return {
  { "olimorris/onedarkpro.nvim", priority = 1000 },
  { "catppuccin", enabled = false },

  -- Configure LazyVim to load catppuccin
  {
    "LazyVim/LazyVim",
    opts = {
      colorscheme = "onedark_vivid",
    },
  },
}
