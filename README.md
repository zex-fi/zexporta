
# Zellular Exchange Deposit

This is the portal module for Zellular Exchange (ZEX), which monitors the deposit and withdraw transaction to ZEX wallets and employs Pyfrost to issue a schnorr signature. The highlevel structure of this module is demonstrated in the figure below:

![Zexporta Structure](./images/zex-flow.png "Figure 1: Zexporta Structure")

# Contribution guide
To contribute to this project, after making your changes, you must write your commit using `cz`.
For doing this you just have to run this command.
```sh
git add -A
cz commit
```
**Note**: please read all kind of commits carefully and be sure about choosing right commit messages.
**Note**: If your changes doesn't have any `Breaking Change` left it empty.
