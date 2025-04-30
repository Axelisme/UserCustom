return {
  "chrisgrieser/nvim-rip-substitute",
  event = "VeryLazy",
  cmd = "RipSubstitute",
  keys = {
    {
      "g/",
      function()
        require("rip-substitute").sub()
      end,
      mode = { "n", "x" }, -- n=Normal, x=Visual
      desc = "Rip Substitute",
    },
  },
}
