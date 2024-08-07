local use_kitty = os.getenv("KITTY_WINDOW_ID") ~= nil

return {
  { "benlubas/image-save.nvim", cmd = "SaveImage" },
  { "leafo/magick", lazy = true },
  {
    "3rd/image.nvim",
    -- enabled = false,
    lazy = not use_kitty,
    dependencies = { "leafo/magick" },
    opts = {
      backend = "kitty",
      integrations = {
        markdown = {
          enabled = true,
          clear_in_insert_mode = false,
          download_remote_images = false,
          only_render_image_at_cursor = false,
          filetypes = { "markdown", "quarto" }, -- markdown extensions (ie. quarto) can go here
        },
        neorg = { enabled = true },
      },
      max_width = 100,
      max_height = 8,
      max_height_window_percentage = math.huge,
      max_width_window_percentage = math.huge,
      window_overlap_clear_enabled = true, -- toggles images when windows are overlapped
      window_overlap_clear_ft_ignore = { "cmp_menu", "cmp_docs", "fidget", "" },
    },
  },
  {
    "nvim-neo-tree/neo-tree.nvim",
    branch = "v3.x",
    dependencies = use_kitty and { "3rd/image.nvim" } or {},
    opts = {
      window = {
        mappings = {
          ["P"] = { "toggle_preview", config = { use_float = false, use_image_nvim = use_kitty } },
        },
      },
    },
  },
}
