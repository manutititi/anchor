# 📖 anc - Simple Anchor System for Directories and Files

## 🎯 Navigation

- `anc set [name]`  
  ⚓ Set anchor (default if no name)

- `anc <name>`  
  ⚓ Go to the specified anchor

- `anc <name> ls`  
  📂 List contents of anchor directory

- `anc <name> tree`  
  🌲 Tree view of anchor directory

- `anc`  
  ⚓ Go to the 'default' anchor

- `anc ls`  
  📌 List all anchors with notes

## 🛠️ Management

- `anc del <name>`  
  🗑️ Delete the specified anchor

- `anc prune`  
  🧹 Delete all anchors

- `anc rename <old> <new>`  
  🔄 Rename an anchor

- `anc note <name> [message]`  
  📝 Add or update note for an anchor

## 📂 File Operations

- `anc cp <file> <anchor>/path`  
  📁 Copy file to anchor subpath

- `anc mv <file> <anchor>/path`  
  🚚 Move file to anchor subpath
