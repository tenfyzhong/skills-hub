---
name: install-nvim-plugin
description: Install a Neovim plugin configuration from a GitHub URL. Usage '/install-nvim-plugin <github-url>'. Parses the URL, fetches plugin documentation, generates optimal lazy.nvim configuration with lazy loading, and saves to `./lua/plugins/`. Optionally updates README.md.
---

# Install Plugin Skill

Install a new Neovim plugin configuration from a GitHub URL with optimal lazy loading.

## Input Format

```
/install-nvim-plugin <github-url>
```

Examples:

- `/install-nvim-plugin https://github.com/folke/flash.nvim`
- `/install-nvim-plugin github.com/nvim-treesitter/nvim-treesitter-textobjects`
- `/install-nvim-plugin folke/noice.nvim`

## Workflow

### Step 1: Parse GitHub URL

Extract owner and repo name from the URL:

```
Input: https://github.com/folke/flash.nvim
       github.com/author/plugin-name
       author/plugin-name

Output:
  - owner: folke
  - repo: flash.nvim
  - plugin_name: flash (derived from repo, removing .nvim/.vim suffix)
```

### Step 2: Fetch Plugin Documentation

Use `gh` CLI or web fetch to get plugin README:

```bash
# Get README content
gh api repos/{owner}/{repo}/readme --jq '.content' | base64 -d

# Or fetch raw README
curl -s https://raw.githubusercontent.com/{owner}/{repo}/main/README.md
# Try 'master' branch if 'main' fails
```

**Key information to extract:**

- Plugin purpose and category
- Required dependencies
- Setup/configuration options
- Recommended keymaps
- Lazy loading triggers (commands, events, filetypes)
- Any build steps required

### Step 3: Scan Existing Keymaps (CRITICAL - Conflict Prevention)

**BEFORE configuring any keymaps, you MUST scan ALL existing keymaps to avoid conflicts.**

#### 3.1 Scan Core Keymaps

Read `./lua/keymap.lua` to extract all core keymaps:

```lua
-- Look for patterns like:
vim.keymap.set({ "n" }, "<leader>w", ...)
vim.keymap.set({ "n", "x" }, ";", ...)
```

#### 3.2 Scan All Plugin Keymaps

Read ALL files in `./lua/plugins/*.lua` and extract keymaps from:

```lua
-- Pattern 1: keys table in lazy.nvim spec
keys = {
    { "<leader>ff", ... },
    { "<tab>f", ... },
}

-- Pattern 2: vim.keymap.set in config functions
vim.keymap.set("n", "<leader>ga", ...)

-- Pattern 3: map() helper functions
map("n", "<leader>gb", ...)
```

#### 3.3 Build Keymap Registry

Create a mental registry of ALL existing keymaps:

| Key | Mode | Plugin/Source | Description |
|-----|------|---------------|-------------|
| `<leader>ff` | n | telescope | find files |
| `<leader>w` | n | keymap.lua | save all |
| `<tab>f` | n | hop | hop char |
| `gd` | n | telescope | goto definition |
| `s` | n,x,o | (available) | - |
| ... | ... | ... | ... |

#### 3.4 Conflict Check Rules

When the new plugin recommends keymaps, check:

1. **Exact match**: Same key + same mode = CONFLICT
2. **Prefix conflict**: `<leader>f` conflicts with `<leader>ff` (blocks prefix)
3. **Mode overlap**: `{ "n", "x" }` overlaps with `{ "n" }` = CONFLICT

#### 3.5 Conflict Resolution

If a recommended keymap conflicts:

1. **DO NOT use the conflicting keymap**
2. **Find alternative** based on plugin category:
   - Motion plugins: Try `<tab>` prefix, `s`, `S`, `gs`, `gz`
   - Git plugins: Try `<leader>g` + available letter
   - LSP plugins: Try `<leader>l` + available letter
   - File plugins: Try `<leader>f` + available letter
   - General: Try `<leader>` + plugin initial + action
3. **Document the change**: Note in output that keymap was changed from default

#### 3.6 Common Available Key Patterns

These are typically safe (but VERIFY first):

- `<leader>` + 2-3 letter combos not in use
- `<localleader>` prefix (`,` in this config)
- `]` and `[` for next/prev actions
- `g` prefix combinations (`gz`, `gx`, etc.)

**IMPORTANT**: Never assume a key is available. ALWAYS verify by scanning.

### Step 4: Determine Lazy Loading Strategy

Based on plugin type, choose the BEST lazy loading approach:

| Plugin Type | Lazy Loading | Example |
|-------------|--------------|---------|
| **UI/Visual** (statusline, colorscheme) | `event = "VeryLazy"` or `priority = 1000` | lualine, material |
| **Keybinding-triggered** (motion, surround) | `keys = {...}` | hop, nvim-surround |
| **Command-triggered** (git, file explorer) | `cmd = {...}` | lazygit, neo-tree |
| **Filetype-specific** (language support) | `ft = {...}` | go.nvim, vim-markdown |
| **LSP-related** | `event = "LspAttach"` | trouble, aerial |
| **Insert mode** (completion, pairs) | `event = "InsertEnter"` | nvim-cmp, autopairs |
| **Buffer read** (syntax, treesitter) | `event = {"BufReadPre", "BufNewFile"}` | treesitter |
| **Git-related** | `event = "VeryLazy"` or on git commands | gitsigns, diffview |

**Priority order for lazy loading (most to least lazy):**

1. `keys` - Only loads when specific key is pressed
2. `cmd` - Only loads when command is executed
3. `ft` - Only loads for specific filetypes
4. `event` - Loads on Vim events
5. No lazy loading - Loads at startup (avoid unless necessary)

### Step 5: Generate Plugin Configuration

Create file at `./lua/plugins/{plugin_name}.lua`

**Template Structure:**

```lua
-- Optional: Helper functions if complex config needed
local function plugin_config()
    require("{plugin_module}").setup({
        -- Configuration options
    })
end

local {plugin_var} = {
    "{owner}/{repo}",
    -- Version pinning (optional but recommended for stability)
    -- tag = "v1.0.0",
    -- branch = "main",

    -- Dependencies (if any)
    dependencies = {
        "nvim-lua/plenary.nvim",
    },

    -- Lazy loading (REQUIRED - choose ONE primary method)
    -- Option A: Key-based (preferred for interactive plugins)
    keys = {
        {
            "<leader>xx",
            function()
                require("{plugin_module}").some_function()
            end,
            desc = "{plugin}: description",
        },
    },

    -- Option B: Command-based
    cmd = { "PluginCommand", "AnotherCommand" },

    -- Option C: Filetype-based
    ft = { "lua", "python" },

    -- Option D: Event-based (least lazy, use sparingly)
    event = "VeryLazy",

    -- Configuration (prefer opts over config when possible)
    opts = {
        -- Simple options
    },

    -- OR use config for complex setup
    config = plugin_config,
    -- OR inline:
    -- config = function()
    --     require("{plugin_module}").setup({})
    -- end,

    -- Build step (if required)
    -- build = "make",
    -- build = ":TSUpdate",
}

return { {plugin_var} }
```

### Step 6: Follow Existing Patterns

**CRITICAL**: Read 2-3 similar existing plugins in `./lua/plugins/` to match:

- Code style (indentation, spacing)
- Naming conventions
- Key mapping patterns (leader key is `'`)
- Config function patterns

**Reference files by plugin type:**

- Motion/navigation: `hop.lua`, `nvim-surround.lua`
- Git: `gitsigns.lua`, `diffview.lua`
- LSP/completion: `telescope.lua`, `nvim-cmp.lua`
- UI: `lualine.lua`, `neo-tree.lua`
- Filetype: `go.lua`, `vim-markdown.lua`

### Step 7: Write the Plugin File

Save to: `./lua/plugins/{plugin_name}.lua`

**Naming rules:**

- Use lowercase
- Replace `.nvim` or `.vim` suffix with nothing
- Use hyphens for multi-word names (e.g., `todo-comments.lua`)

### Step 8: Update README.md (If Significant)

Only update README.md if the plugin:

- Adds new key mappings users should know
- Adds new commands
- Requires external tool installation
- Is a major feature addition

**Update sections:**

- Add to appropriate "Plugin Categories" section
- Add key mappings to "Key Mappings" section if applicable
- Add to "Required External Tools" if dependencies needed

## Output Format

After creating the plugin:

```
✅ Created plugin: ./lua/plugins/{plugin_name}.lua

**Plugin**: {owner}/{repo}
**Lazy Loading**: {method} ({trigger})
**Dependencies**: {list or "None"}

**Key Mappings** (if any):
| Key | Action |
|-----|--------|
| ... | ... |

**Commands** (if any):
- :Command1
- :Command2

**Notes**:
- {Any special setup instructions}
- {External tools needed}
```

## Examples

### Example 1: Motion Plugin (key-based lazy loading)

Input: `/install-nvim-plugin https://github.com/folke/flash.nvim`

Output file `./lua/plugins/flash.lua`:

```lua
local flash = {
    "folke/flash.nvim",
    event = "VeryLazy",
    opts = {
        modes = {
            search = { enabled = false },
        },
    },
    keys = {
        {
            "s",
            function()
                require("flash").jump()
            end,
            mode = { "n", "x", "o" },
            desc = "flash: jump",
        },
        {
            "S",
            function()
                require("flash").treesitter()
            end,
            mode = { "n", "x", "o" },
            desc = "flash: treesitter",
        },
    },
}

return { flash }
```

### Example 2: Command-based Plugin

Input: `/install-nvim-plugin https://github.com/sindrets/diffview.nvim`

Output file `./lua/plugins/diffview.lua`:

```lua
local diffview = {
    "sindrets/diffview.nvim",
    dependencies = { "nvim-lua/plenary.nvim" },
    cmd = { "DiffviewOpen", "DiffviewFileHistory" },
    opts = {
        enhanced_diff_hl = true,
    },
}

return { diffview }
```

### Example 3: Filetype-specific Plugin

Input: `/install-nvim-plugin https://github.com/iamcco/markdown-preview.nvim`

Output file `./lua/plugins/markdown-preview.lua`:

```lua
local markdown_preview = {
    "iamcco/markdown-preview.nvim",
    ft = { "markdown" },
    build = function()
        vim.fn["mkdp#util#install"]()
    end,
    keys = {
        {
            "<leader>mp",
            "<cmd>MarkdownPreviewToggle<cr>",
            ft = "markdown",
            desc = "markdown-preview: toggle",
        },
    },
}

return { markdown_preview }
```

## Important Notes

1. **Always lazy load** - Never load plugins at startup unless absolutely necessary
2. **Prefer `keys` or `cmd`** - These are the laziest loading methods
3. **Match existing style** - Read similar plugins first
4. **Test the config** - Verify syntax is correct before finishing
5. **Minimal config** - Start with minimal setup, user can customize later
6. **Document keymaps** - Always include `desc` for key mappings
7. **Check for conflicts** - Ensure keymaps don't conflict with existing ones

## Checklist Before Completion

- [ ] Plugin file created at correct path
- [ ] Lazy loading strategy chosen and implemented
- [ ] Dependencies listed (if any)
- [ ] Key mappings have descriptions
- [ ] Code style matches existing plugins
- [ ] No syntax errors (run `lua -c` or check with LSP)
- [ ] README.md updated (if significant plugin)
