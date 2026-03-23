import torch
import torch.nn as nn

class SpatialAttention(nn.Module):
    def __init__(self, num_channels):
        super(SpatialAttention, self).__init__()
        # Squeeze-and-Excitation: Learns which electrodes are most important
        self.fc1 = nn.Linear(num_channels, num_channels // 2)
        self.fc2 = nn.Linear(num_channels // 2, num_channels)
        
    def forward(self, x):
        w = torch.mean(x, dim=2) 
        w = torch.relu(self.fc1(w))
        w = torch.sigmoid(self.fc2(w)).unsqueeze(2)
        return x * w 

class SEED_SICNet8_Attention(nn.Module):
    def __init__(self, num_channels=8):
        super(SEED_SICNet8_Attention, self).__init__()
        self.conv1 = nn.Conv1d(num_channels, 64, kernel_size=3, padding=1)
        self.bn1 = nn.BatchNorm1d(64)
        
        self.conv2 = nn.Conv1d(num_channels, 64, kernel_size=5, padding=2)
        self.bn2 = nn.BatchNorm1d(64)
        
        self.attention = SpatialAttention(128) 
        
        self.classifier = nn.Sequential(
            nn.Linear(128, 64),
            nn.LayerNorm(64),
            nn.ReLU(),
            nn.Dropout(0.5),
            nn.Linear(64, 4) # 0: Neutral, 1: Sad, 2: Fear, 3: Happy
        )

    def forward(self, x):
        x1 = torch.relu(self.bn1(self.conv1(x)))
        x2 = torch.relu(self.bn2(self.conv2(x)))
        x_fusion = torch.cat([x1, x2], dim=1) 
        x_attended = self.attention(x_fusion)
        x_pooled = torch.mean(x_attended, dim=2) 
        return self.classifier(x_pooled)