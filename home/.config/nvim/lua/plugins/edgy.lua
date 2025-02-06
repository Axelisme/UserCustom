return {
  "folke/edgy.nvim",
  keys = {
    -- resize windows in terminal mode
    { "<C-Up>", "<cmd>lua require('edgy').get_win():resize('height', 2)<CR>", mode = "t" },
    { "<C-Down>", "<cmd>lua require('edgy').get_win():resize('height', -2)<CR>", mode = "t" },
  },
  opts = function(_, opts)
    opts.animate = { enabled = false }
    opts.wo = { winbar = "" }

    -- disable show buffer and git status in neo-tree
    if pcall(require, "neo-tree") then
      opts.left = vim.tbl_filter(function(panel)
        return panel.title ~= "Neo-Tree Filesystem"
      end, opts.left)
    end
  end,
}
