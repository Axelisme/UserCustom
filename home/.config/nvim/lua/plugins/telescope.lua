return {
  "nvim-telescope/telescope.nvim",
  keys = {
    { "<leader><space>", "<cmd>Telescope find_files<CR>", desc = "Find Files (cwd)" },
    { "<leader>ff", "<cmd>Telescope find_files<CR>", desc = "Find Files (cwd)" },
    { "<leader>fF", LazyVim.pick("files"), desc = "Find Files (Root Dir)" },
  },
}
