return {
  {
    "kevinhwang91/nvim-ufo",
    dependencies = "kevinhwang91/promise-async",
    event = "BufReadPost",
    keys = {
      { "zR", "<cmd>lua require('ufo').openAllFolds()<CR>" },
      { "zM", "<cmd>lua require('ufo').closeAllFolds()<CR>" },
      { "zr", "zR", { remap = true } },
      { "zm", "zM", { remap = true } },
    },
    init = function()
      vim.opt.foldmethod = "indent"
      vim.opt.foldenable = true
      vim.opt.foldlevel = 99
      vim.opt.foldlevelstart = 99
      vim.opt.foldnestmax = 99
    end,
    opts = {
      open_fold_hl_timeout = 150,
      fold_virt_text_handler = M.foldtext,
      close_fold_kinds_for_ft = {
        default = { "imports", "comment" },
        json = { "array" },
        c = { "comment", "region" },
      },
      provider_selector = function()
        return { "treesitter", "indent" }
      end,
    },
  },
}
